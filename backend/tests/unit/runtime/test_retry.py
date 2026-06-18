"""Unit tests for per-node retry/backoff."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.runtime.errors import ToolArgValidationError, ToolCallAmbiguousError, ToolExecutionError
from app.runtime.retry import RetryPolicy, with_retry
from app.runtime.state import RunState


def make_state(**kwargs: Any) -> RunState:
    base: RunState = {
        "run_id": "run-1",
        "messages": [],
        "output": None,
        "step_index": 0,
        "error": None,
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


async def test_succeeds_on_first_attempt_no_retry() -> None:
    calls = 0

    async def handler(state: RunState) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"ok": True}

    wrapped = with_retry(handler, "n1", RetryPolicy(max_retries=3, base_backoff_seconds=0), None)
    result = await wrapped(make_state())

    assert result == {"ok": True}
    assert calls == 1


async def test_transient_exception_retries_then_succeeds() -> None:
    calls = 0

    async def handler(state: RunState) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("slow")
        return {"ok": True}

    wrapped = with_retry(handler, "n1", RetryPolicy(max_retries=3, base_backoff_seconds=0), None)
    result = await wrapped(make_state())

    assert result == {"ok": True}
    assert calls == 3


async def test_transient_exception_raises_after_exhausting_retries() -> None:
    calls = 0

    async def handler(state: RunState) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise ToolExecutionError("tool 5xx")

    wrapped = with_retry(handler, "n1", RetryPolicy(max_retries=2, base_backoff_seconds=0), None)

    with pytest.raises(ToolExecutionError):
        await wrapped(make_state())

    assert calls == 3  # initial attempt + 2 retries


async def test_permanent_exception_skips_retry() -> None:
    calls = 0

    async def handler(state: RunState) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise ToolArgValidationError("bad args")

    wrapped = with_retry(handler, "n1", RetryPolicy(max_retries=3, base_backoff_seconds=0), None)

    with pytest.raises(ToolArgValidationError):
        await wrapped(make_state())

    assert calls == 1


async def test_ambiguous_exception_skips_retry() -> None:
    calls = 0

    async def handler(state: RunState) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        raise ToolCallAmbiguousError("unknown outcome")

    wrapped = with_retry(handler, "n1", RetryPolicy(max_retries=3, base_backoff_seconds=0), None)

    with pytest.raises(ToolCallAmbiguousError):
        await wrapped(make_state())

    assert calls == 1


async def test_emits_retry_event_with_correct_attempt_numbers() -> None:
    calls = 0

    async def handler(state: RunState) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("slow")
        return {"ok": True}

    emitter = AsyncMock()
    wrapped = with_retry(handler, "n1", RetryPolicy(max_retries=3, base_backoff_seconds=0), emitter)
    await wrapped(make_state(step_index=7))

    assert emitter.emit.call_count == 2
    attempts = [c.kwargs["payload"]["attempt"] for c in emitter.emit.call_args_list]
    assert attempts == [1, 2]
    for c in emitter.emit.call_args_list:
        assert c.kwargs["event_type"] == "retry"
        assert c.kwargs["node_id"] == "n1"
        assert c.kwargs["step_index"] == 7
