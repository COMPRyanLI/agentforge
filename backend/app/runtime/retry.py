"""Retry with exponential backoff — generic primitive plus a per-node wrapper.

retry_async() retries a single awaitable-producing callable. with_retry()
wraps a whole NodeHandler at GraphCompiler construction time, for node types
where retrying the entire node is safe (input/tool/output — see compiler.py;
the llm node retries individual llm.chat()/tool calls internally instead,
via retry_async directly, because retrying its whole node would silently
re-issue already-completed LLM calls — non-idempotent and not what
"transient failure, retry" should mean for an external model call).

Replay-safety: the only wall-clock read here (datetime.now(UTC)) stamps a
`retry` event log entry, the same pattern already used in handlers.py — it
never feeds into control flow or state. asyncio.sleep for backoff is pure
delay, not an external-state read, so it's safe inside a checkpointed node.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.runtime.errors import ToolCallAmbiguousError, ToolExecutionError
from app.runtime.state import NodeHandler, RunState

if TYPE_CHECKING:
    from app.runtime.event_emitter import EventEmitter

# Transient: worth retrying — likely a timeout/network blip that may succeed
# on a later attempt. ToolCallAmbiguousError is deliberately NOT here: retrying
# it could double-fire a side effect whose outcome is already unknown.
TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (
    TimeoutError,
    ToolExecutionError,
    ConnectionError,
)

# Permanent: retrying can never succeed (bad graph, bad args, unknown tool,
# or an ambiguous idempotency state that must be resolved by a human).
PERMANENT_EXCEPTIONS: tuple[type[Exception], ...] = (ToolCallAmbiguousError,)


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_backoff_seconds: float = 1.0


async def retry_async[T](
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    on_retry: Callable[[int, Exception], Awaitable[None]] | None = None,
) -> T:
    """Retry a single awaitable-producing callable with exponential backoff.

    on_retry(attempt, exc) is called before each backoff sleep (attempt is
    1-indexed: the attempt number that just failed). Permanent failures
    (PERMANENT_EXCEPTIONS, or anything not in TRANSIENT_EXCEPTIONS) propagate
    immediately without retrying.
    """
    last_exc: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        try:
            return await fn()
        except PERMANENT_EXCEPTIONS:
            raise
        except TRANSIENT_EXCEPTIONS as exc:
            last_exc = exc
            if attempt >= policy.max_retries:
                raise
            if on_retry is not None:
                await on_retry(attempt + 1, exc)
            await asyncio.sleep(policy.base_backoff_seconds * (2**attempt))
    # Unreachable: the loop either returns or raises on its last iteration.
    assert last_exc is not None
    raise last_exc


def with_retry(
    handler: NodeHandler,
    node_id: str,
    policy: RetryPolicy,
    event_emitter: EventEmitter | None,
) -> NodeHandler:
    """Wrap an entire NodeHandler so transient failures retry the whole node.

    Only safe for node types whose full body is idempotent to re-run from
    scratch (input/tool/output) — see compiler.py, which does NOT apply this
    to the llm node.
    """

    async def _wrapped(state: RunState) -> dict[str, Any]:
        async def _on_retry(attempt: int, exc: Exception) -> None:
            if event_emitter is not None:
                await event_emitter.emit(
                    step_index=state["step_index"],
                    node_id=node_id,
                    event_type="retry",
                    payload={"attempt": attempt, "error": str(exc)},
                    ts=datetime.now(UTC),
                )

        return await retry_async(lambda: handler(state), policy, _on_retry)

    return _wrapped
