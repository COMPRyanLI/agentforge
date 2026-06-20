"""Unit tests for node handler factories.

Uses a mock LLMProvider — no real Ollama required.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

from app.llm.provider import LLMProvider, LLMResponse, ToolCall
from app.runtime.builtins import register_builtins
from app.runtime.handlers import (
    MAX_TOOL_ITERATIONS,
    make_input_handler,
    make_llm_handler,
    make_output_handler,
    make_tool_handler,
)
from app.runtime.registry import RegisteredTool, ToolRegistry
from app.runtime.retry import RetryPolicy
from app.runtime.state import RunState
from tests.unit.runtime.conftest import FakeToolCallRepo, dummy_session_factory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_state(**kwargs: Any) -> RunState:
    base: RunState = {
        "run_id": str(uuid.uuid4()),
        "messages": [{"role": "user", "content": "hello"}],
        "output": None,
        "step_index": 0,
        "error": None,
    }
    base.update(kwargs)  # type: ignore[typeddict-item]
    return base


def make_registry() -> ToolRegistry:
    r = ToolRegistry()
    register_builtins(r)
    return r


# ---------------------------------------------------------------------------
# input handler
# ---------------------------------------------------------------------------


async def test_input_handler_is_passthrough() -> None:
    handler = make_input_handler()
    state = make_state()
    update = await handler(state)
    assert update == {}


# ---------------------------------------------------------------------------
# output handler
# ---------------------------------------------------------------------------


async def test_output_handler_extracts_last_assistant_content() -> None:
    handler = make_output_handler()
    state = make_state(
        messages=[
            {"role": "user", "content": "what is 2+2?"},
            {"role": "assistant", "content": "It is 4."},
        ]
    )
    update = await handler(state)
    assert update["output"] == "It is 4."


async def test_output_handler_returns_none_when_no_assistant_message() -> None:
    handler = make_output_handler()
    state = make_state(messages=[{"role": "user", "content": "hi"}])
    update = await handler(state)
    assert update["output"] is None


async def test_output_handler_skips_tool_call_turn_with_no_content() -> None:
    handler = make_output_handler()
    state = make_state(
        messages=[
            {"role": "user", "content": "calc"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"function": {"name": "calculator"}}],
            },
            {"role": "tool", "content": "42"},
            {"role": "assistant", "content": "The answer is 42."},
        ]
    )
    update = await handler(state)
    assert update["output"] == "The answer is 42."


# ---------------------------------------------------------------------------
# llm handler — no tools
# ---------------------------------------------------------------------------


async def test_llm_handler_no_tools_single_call() -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="Hi there!", tool_calls=[])  # type: ignore[attr-defined]

    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="You are helpful.",
        session_factory=dummy_session_factory,
    )
    state = make_state()
    update = await handler(state)

    mock_llm.chat.assert_called_once()  # type: ignore[attr-defined]
    messages: list[dict[str, Any]] = update["messages"]
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "Hi there!"
    assert update["step_index"] == 1


async def test_llm_handler_prepends_system_message() -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="OK", tool_calls=[])  # type: ignore[attr-defined]

    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="Be concise.",
        session_factory=dummy_session_factory,
    )
    state = make_state()
    await handler(state)

    call_messages = mock_llm.chat.call_args[0][0]  # type: ignore[attr-defined]
    assert call_messages[0]["role"] == "system"
    assert call_messages[0]["content"] == "Be concise."


async def test_llm_handler_does_not_double_prepend_system() -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="OK", tool_calls=[])  # type: ignore[attr-defined]

    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="My prompt.",
        session_factory=dummy_session_factory,
    )
    state = make_state(
        messages=[
            {"role": "system", "content": "Existing system."},
            {"role": "user", "content": "hi"},
        ]
    )
    await handler(state)

    call_messages = mock_llm.chat.call_args[0][0]  # type: ignore[attr-defined]
    system_msgs = [m for m in call_messages if m["role"] == "system"]
    assert len(system_msgs) == 1
    assert system_msgs[0]["content"] == "Existing system."


# ---------------------------------------------------------------------------
# llm handler — with tool call
# ---------------------------------------------------------------------------


async def test_llm_handler_tool_calling_loop_one_round(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="calculator", arguments={"expression": "6*7"})],
        ),
        LLMResponse(content="6 times 7 is 42.", tool_calls=[]),
    ]

    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=["calculator"],
        system_prompt="You are a helpful assistant.",
        session_factory=dummy_session_factory,
    )
    state = make_state(messages=[{"role": "user", "content": "what is 6 times 7?"}])
    update = await handler(state)

    assert mock_llm.chat.call_count == 2  # type: ignore[attr-defined]
    messages: list[dict[str, Any]] = update["messages"]

    # Check the tool result was appended
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "calculator" in tool_msgs[0]["content"] or "42" in tool_msgs[0]["content"]

    # Final assistant message has the answer
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "6 times 7 is 42."


async def test_llm_handler_retries_only_the_failed_tool_call_not_earlier_llm_calls(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    """Pins the fix for the bug where with_retry wrapped the whole llm node:
    a transient failure on a tool call must retry only that call, never
    re-issue the llm.chat() call that already succeeded earlier in this
    same attempt."""
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="flaky", arguments={"x": 1})],
        ),
        LLMResponse(content="done", tool_calls=[]),
    ]

    impl_calls = 0

    async def _flaky_impl(args: dict[str, Any]) -> dict[str, Any]:
        nonlocal impl_calls
        impl_calls += 1
        if impl_calls == 1:
            raise RuntimeError("transient blip")
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="flaky", description="", json_schema={"type": "object"}, impl_fn=_flaky_impl
        )
    )

    handler = make_llm_handler(
        llm=mock_llm,
        registry=registry,
        tool_names=["flaky"],
        system_prompt="",
        session_factory=dummy_session_factory,
        retry_policy=RetryPolicy(max_retries=1, base_backoff_seconds=0),
    )
    state = make_state()
    update = await handler(state)

    # The tool's impl_fn was retried once (failed, then succeeded)...
    assert impl_calls == 2
    # ...but llm.chat() was only ever called the two times the loop logic
    # requires (initial call returning the tool_calls, final call after the
    # tool result) — never re-issued because of the tool's internal retry.
    assert mock_llm.chat.call_count == 2  # type: ignore[attr-defined]
    assert update["messages"][-1]["content"] == "done"


async def test_llm_handler_increments_step_index() -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="done", tool_calls=[])  # type: ignore[attr-defined]

    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="",
        session_factory=dummy_session_factory,
    )
    state = make_state(step_index=5)
    update = await handler(state)
    assert update["step_index"] == 6


async def test_llm_handler_max_iterations_guard(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    """When LLM always returns tool calls, the loop exits after MAX_TOOL_ITERATIONS."""
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    # Always return a tool call — should exit after MAX_TOOL_ITERATIONS
    mock_llm.chat.return_value = LLMResponse(  # type: ignore[attr-defined]
        content=None,
        tool_calls=[ToolCall(name="calculator", arguments={"expression": "1+1"})],
    )

    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=["calculator"],
        system_prompt="",
        session_factory=dummy_session_factory,
    )
    state = make_state()
    update = await handler(state)

    # Exactly MAX_TOOL_ITERATIONS LLM calls, then loop exits
    assert mock_llm.chat.call_count == MAX_TOOL_ITERATIONS  # type: ignore[attr-defined]
    assert "messages" in update


# ---------------------------------------------------------------------------
# standalone tool handler
# ---------------------------------------------------------------------------


async def test_tool_handler_invokes_tool(fake_tool_call_repo: FakeToolCallRepo) -> None:
    handler = make_tool_handler(make_registry(), "calculator", dummy_session_factory)
    state = make_state(
        messages=[
            {"role": "user", "content": "calc"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": {"expression": "3+3"}}}
                ],
            },
        ]
    )
    update = await handler(state)
    messages: list[dict[str, Any]] = update["messages"]
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert "6" in tool_msgs[0]["content"]


async def test_tool_handler_increments_step_index(fake_tool_call_repo: FakeToolCallRepo) -> None:
    handler = make_tool_handler(make_registry(), "calculator", dummy_session_factory)
    state = make_state(
        step_index=3,
        messages=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": {"expression": "1+1"}}}
                ],
            },
        ],
    )
    update = await handler(state)
    assert update["step_index"] == 4


# ---------------------------------------------------------------------------
# EventEmitter integration — existing tests must pass with event_emitter=None
# ---------------------------------------------------------------------------


async def test_input_handler_without_emitter_unchanged() -> None:
    handler = make_input_handler(node_id="in")
    update = await handler(make_state())
    assert update == {}


async def test_llm_handler_emits_node_start_and_end() -> None:
    from unittest.mock import AsyncMock as _AM

    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="ok", tool_calls=[])  # type: ignore[attr-defined]

    emitter = _AM()
    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="Be helpful.",
        session_factory=dummy_session_factory,
        node_id="llm1",
        event_emitter=emitter,
    )
    await handler(make_state())

    called_types = [c.kwargs["event_type"] for c in emitter.emit.call_args_list]
    assert "node_start" in called_types
    assert "node_end" in called_types


async def test_llm_handler_emits_tool_call_and_result_events(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    from unittest.mock import AsyncMock as _AM

    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(name="calculator", arguments={"expression": "1+1"})],
        ),
        LLMResponse(content="2", tool_calls=[]),
    ]

    emitter = _AM()
    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=["calculator"],
        system_prompt="",
        session_factory=dummy_session_factory,
        node_id="llm1",
        event_emitter=emitter,
    )
    await handler(make_state())

    called_types = [c.kwargs["event_type"] for c in emitter.emit.call_args_list]
    assert "tool_call" in called_types
    assert "tool_result" in called_types


async def test_tool_handler_emits_events_when_emitter_provided(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    from unittest.mock import AsyncMock as _AM

    emitter = _AM()
    handler = make_tool_handler(
        make_registry(),
        "calculator",
        dummy_session_factory,
        node_id="t1",
        event_emitter=emitter,
    )
    state = make_state(
        messages=[
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": {"expression": "2+2"}}}
                ],
            }
        ]
    )
    await handler(state)

    called_types = [c.kwargs["event_type"] for c in emitter.emit.call_args_list]
    assert "node_start" in called_types
    assert "tool_call" in called_types
    assert "tool_result" in called_types
    assert "node_end" in called_types


async def test_llm_handler_emits_usage_fields_in_llm_result(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    from unittest.mock import AsyncMock as _AM

    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(  # type: ignore[attr-defined]
        content="ok",
        tool_calls=[],
        prompt_tokens=10,
        completion_tokens=20,
        total_duration_ms=123.4,
    )

    emitter = _AM()
    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="",
        session_factory=dummy_session_factory,
        node_id="llm1",
        event_emitter=emitter,
    )
    await handler(make_state())

    llm_result_calls = [
        c for c in emitter.emit.call_args_list if c.kwargs["event_type"] == "llm_result"
    ]
    assert len(llm_result_calls) == 1
    payload = llm_result_calls[0].kwargs["payload"]
    assert payload["prompt_tokens"] == 10
    assert payload["completion_tokens"] == 20
    assert payload["total_duration_ms"] == 123.4


async def test_llm_handler_emits_none_usage_fields_when_provider_omits_them(
    fake_tool_call_repo: FakeToolCallRepo,
) -> None:
    from unittest.mock import AsyncMock as _AM

    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="ok", tool_calls=[])  # type: ignore[attr-defined]

    emitter = _AM()
    handler = make_llm_handler(
        llm=mock_llm,
        registry=make_registry(),
        tool_names=[],
        system_prompt="",
        session_factory=dummy_session_factory,
        node_id="llm1",
        event_emitter=emitter,
    )
    await handler(make_state())

    llm_result_calls = [
        c for c in emitter.emit.call_args_list if c.kwargs["event_type"] == "llm_result"
    ]
    payload = llm_result_calls[0].kwargs["payload"]
    assert payload["prompt_tokens"] is None
    assert payload["completion_tokens"] is None
    assert payload["total_duration_ms"] is None


async def test_output_handler_emits_events_when_emitter_provided() -> None:
    from unittest.mock import AsyncMock as _AM

    emitter = _AM()
    handler = make_output_handler(node_id="out", event_emitter=emitter)
    state = make_state(messages=[{"role": "assistant", "content": "done"}])
    await handler(state)

    called_types = [c.kwargs["event_type"] for c in emitter.emit.call_args_list]
    assert "node_start" in called_types
    assert "node_end" in called_types
