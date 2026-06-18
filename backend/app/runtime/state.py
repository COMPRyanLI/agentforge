"""Shared run state threaded through every LangGraph node.

Must remain JSON-serializable: Phase 4 will attach a Postgres checkpointer
that serialises this dict. Use str for UUIDs, not uuid.UUID objects.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from typing_extensions import TypedDict

# Re-use the same open-ended message type as LLMProvider so handlers can
# pass state["messages"] directly to provider.chat() without conversion.
Message = dict[str, Any]  # justified: Ollama message format is open-ended


class RunState(TypedDict):
    run_id: str  # UUID as string; set once at graph entry, never mutated
    messages: list[Message]  # full conversation history (user + assistant + tool turns)
    output: str | None  # final answer, set by the output node
    step_index: int  # incremented by handlers; used to derive idempotency keys
    error: str | None  # non-None means a handler caught an unrecoverable error
    # Per-loop-node iteration counters, keyed by node_id. Checkpointed like every
    # other field (plain overwrite semantics) — this is what lets a crash mid-loop
    # resume at the correct iteration instead of restarting the loop.
    loop_counters: dict[str, int]


# Lives here (not handlers.py) so app.runtime.retry can depend on the type
# without creating a handlers.py <-> retry.py import cycle.
NodeHandler = Callable[[RunState], Awaitable[dict[str, Any]]]
