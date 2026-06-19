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
    # resume at the correct iteration instead of restarting the loop. Never exceeds
    # the node's max_iterations — make_loop_handler only advances it when actually
    # continuing into the loop body.
    loop_counters: dict[str, int]
    # Per-loop-node continue/exit decision, keyed by node_id, written by
    # make_loop_handler and read by GraphCompiler's conditional-edge route function.
    # The route function only ever sees state *after* the handler ran, where a
    # legitimate "just performed iteration N" visit and a later "max_iterations
    # already reached" visit can show the identical loop_counters value — so the
    # decision is precomputed here (where the pre-increment counter is visible)
    # rather than re-derived ambiguously from the counter alone.
    loop_continue: dict[str, bool]


# Lives here (not handlers.py) so app.runtime.retry can depend on the type
# without creating a handlers.py <-> retry.py import cycle.
NodeHandler = Callable[[RunState], Awaitable[dict[str, Any]]]
