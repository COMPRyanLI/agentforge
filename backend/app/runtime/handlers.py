"""Node handler factories for the agent runtime.

Each factory returns a coroutine that takes RunState and returns a partial
state update dict (LangGraph merges it). Handlers are pure closures: the
LLMProvider and ToolRegistry are bound at compile time, never looked up
at runtime. This is the key replay-safety guarantee.

Replay-safety rules (enforced here):
- No datetime.now(), random, or uuid4() calls inside any handler's control
  flow logic. datetime.now(UTC) is called only to stamp event log entries —
  a recorded side effect, not a value that influences routing or LLM input.
- step_index is incremented explicitly in state (not derived from LangGraph
  internals) so it survives checkpointing and remains stable on replay.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import LLMProvider
from app.runtime.errors import AgentRuntimeError, GraphCompilationError
from app.runtime.expr import ExprEvaluationError, evaluate_condition, namespace_from_state
from app.runtime.registry import ToolRegistry, invoke_tool_idempotent
from app.runtime.retry import RetryPolicy, retry_async
from app.runtime.state import Message, NodeHandler, RunState

if TYPE_CHECKING:
    from app.runtime.event_emitter import EventEmitter

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 10


async def _maybe_emit(
    emitter: EventEmitter | None,
    step_index: int,
    node_id: str,
    event_type: str,
    payload: dict[str, Any],  # justified: event payload is open-ended
    ts: datetime,
) -> None:
    if emitter is not None:
        await emitter.emit(
            step_index=step_index,
            node_id=node_id,
            event_type=event_type,
            payload=payload,
            ts=ts,
        )


def make_input_handler(
    node_id: str = "input",
    event_emitter: EventEmitter | None = None,
) -> NodeHandler:
    """Input node: passthrough.

    The user message is already placed in state["messages"] by the executor
    before graph invocation, so this node is a no-op. It exists as an explicit
    entry point so the graph structure mirrors the canvas node layout.
    """

    async def _handler(state: RunState) -> dict[str, Any]:
        ts = datetime.now(UTC)
        await _maybe_emit(event_emitter, state["step_index"], node_id, "node_start", {}, ts)
        await _maybe_emit(event_emitter, state["step_index"], node_id, "node_end", {}, ts)
        return {}

    return _handler


_DEFAULT_RETRY_POLICY = RetryPolicy()


def make_llm_handler(
    llm: LLMProvider,
    registry: ToolRegistry,
    tool_names: list[str],
    system_prompt: str,
    session_factory: async_sessionmaker[AsyncSession],
    retry_policy: RetryPolicy = _DEFAULT_RETRY_POLICY,
    node_id: str = "llm",
    event_emitter: EventEmitter | None = None,
) -> NodeHandler:
    """LLM node with an internal tool-calling loop.

    Calls the LLM, and if it returns tool_calls, invokes each tool, appends
    the results to messages, and calls the LLM again — up to MAX_TOOL_ITERATIONS
    times. Once the LLM returns plain content, the loop ends.

    The loop is intentionally contained inside this node for Phase 2 simplicity.

    Retry: GraphCompiler does NOT wrap this node's handler with with_retry like
    it does input/tool/output. Retrying the whole node would silently re-issue
    every llm.chat() call already made earlier in this same attempt (the loop
    has no per-call checkpoint to resume from) — non-idempotent and not what a
    "transient failure, retry" policy should mean for an external model call.
    Instead, each individual llm.chat() call and each invoke_tool_idempotent()
    call is retried on its own via retry_async — a failed 3rd tool call retries
    just that call, never redoing the first two LLM calls or their already-
    completed (idempotency-guarded) tool invocations.
    """
    tool_schemas = registry.to_llm_schemas(tool_names) if tool_names else None

    async def _handler(state: RunState) -> dict[str, Any]:
        ts = datetime.now(UTC)
        step = state["step_index"]
        messages: list[Message] = list(state["messages"])

        async def _on_retry(attempt: int, exc: Exception) -> None:
            await _maybe_emit(
                event_emitter,
                step,
                node_id,
                "retry",
                {"attempt": attempt, "error": str(exc)},
                datetime.now(UTC),
            )

        await _maybe_emit(event_emitter, step, node_id, "node_start", {}, ts)

        # Prepend system message if absent. Explicit Message annotation ensures
        # the concat result is list[Message] (not list[dict[str, str]]).
        if not messages or messages[0].get("role") != "system":
            sys_msg: Message = {"role": "system", "content": system_prompt}
            messages = [sys_msg] + messages

        # Counts tool calls across the whole node invocation (not reset per LLM
        # iteration) — step_index stays fixed for this entire handler call, so
        # call_index alone must disambiguate every tool call made within it.
        call_index = 0

        for _ in range(MAX_TOOL_ITERATIONS):
            await _maybe_emit(
                event_emitter, step, node_id, "llm_call", {"message_count": len(messages)}, ts
            )

            async def _call_llm() -> Any:
                return await llm.chat(messages, tools=tool_schemas)

            response = await retry_async(_call_llm, retry_policy, _on_retry)

            if not response.tool_calls:
                await _maybe_emit(
                    event_emitter,
                    step,
                    node_id,
                    "llm_result",
                    {"content_preview": (response.content or "")[:200]},
                    ts,
                )
                text_msg: Message = {"role": "assistant", "content": response.content}
                messages.append(text_msg)
                break

            # Build the assistant's tool-call turn in Ollama native format
            assistant_msg: Message = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Invoke each tool and append results
            for tc in response.tool_calls:
                await _maybe_emit(
                    event_emitter,
                    step,
                    node_id,
                    "tool_call",
                    {"tool_name": tc.name, "args": tc.arguments},
                    ts,
                )

                async def _invoke_tool(
                    tool_name: str = tc.name,
                    tool_args: dict[str, Any] = tc.arguments,
                    this_call_index: int = call_index,
                ) -> Any:
                    return await invoke_tool_idempotent(
                        session_factory,
                        registry,
                        tool_name,
                        tool_args,
                        run_id=state["run_id"],
                        node_id=node_id,
                        step_index=step,
                        call_index=this_call_index,
                    )

                result = await retry_async(_invoke_tool, retry_policy, _on_retry)
                call_index += 1
                await _maybe_emit(
                    event_emitter,
                    step,
                    node_id,
                    "tool_result",
                    {"tool_name": tc.name, "result_preview": str(result)[:200]},
                    ts,
                )
                tool_msg: Message = {
                    "role": "tool",
                    "name": tc.name,
                    "content": str(result),
                }
                messages.append(tool_msg)
        else:
            # Exceeded MAX_TOOL_ITERATIONS without a final text response
            logger.warning(
                "run_id=%s llm node hit MAX_TOOL_ITERATIONS (%d)",
                state["run_id"],
                MAX_TOOL_ITERATIONS,
            )

        await _maybe_emit(event_emitter, step, node_id, "node_end", {}, ts)
        return {
            "messages": messages,
            "step_index": step + 1,
        }

    return _handler


def make_tool_handler(
    registry: ToolRegistry,
    tool_name: str,
    session_factory: async_sessionmaker[AsyncSession],
    node_id: str = "tool",
    event_emitter: EventEmitter | None = None,
    require_approval: bool = False,
) -> NodeHandler:
    """Standalone tool node for explicit tool invocations wired in graph_json.

    Extracts the args for `tool_name` from the most recent assistant message's
    tool_calls list, invokes the tool, and appends the result to messages.

    require_approval=True pauses the graph (via LangGraph's interrupt()) for a
    human decision before invoking the tool — see the module docstring's note
    on human-in-the-loop. Args are extracted before the interrupt() call: that
    extraction is a pure read with no side effects, so it's safe to redo when
    this handler re-enters from the top on resume (which it always does —
    interrupt() does not resume mid-function, the whole node re-runs).
    """

    async def _handler(state: RunState) -> dict[str, Any]:
        ts = datetime.now(UTC)
        step = state["step_index"]
        messages: list[Message] = list(state["messages"])

        # Find the most recent assistant message with a matching tool call
        args: dict[str, Any] | None = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    if tc.get("function", {}).get("name") == tool_name:
                        args = tc["function"].get("arguments", {})
                        break
                break

        if args is None:
            raise AgentRuntimeError(
                f"Tool node '{tool_name}': no matching tool call found in message history"
            )

        if require_approval:
            decision = interrupt({"tool_name": tool_name, "args": args, "node_id": node_id})
            if decision != "approved":
                raise AgentRuntimeError(f"Tool call to {tool_name!r} was rejected by approver")

        await _maybe_emit(event_emitter, step, node_id, "node_start", {}, ts)
        await _maybe_emit(
            event_emitter, step, node_id, "tool_call", {"tool_name": tool_name, "args": args}, ts
        )
        result = await invoke_tool_idempotent(
            session_factory,
            registry,
            tool_name,
            args,
            run_id=state["run_id"],
            node_id=node_id,
            step_index=step,
            call_index=0,
        )
        await _maybe_emit(
            event_emitter,
            step,
            node_id,
            "tool_result",
            {"tool_name": tool_name, "result_preview": str(result)[:200]},
            ts,
        )
        messages.append(
            {
                "role": "tool",
                "name": tool_name,
                "content": str(result),
            }
        )
        await _maybe_emit(event_emitter, step, node_id, "node_end", {}, ts)
        return {
            "messages": messages,
            "step_index": step + 1,
        }

    return _handler


def make_condition_handler(
    node_id: str = "condition",
    event_emitter: EventEmitter | None = None,
) -> NodeHandler:
    """Condition node: passthrough.

    The actual branching decision is made by the conditional-edge routing
    function the GraphCompiler attaches via add_conditional_edges (see
    app.runtime.expr / compiler.py) — this handler only exists so the node
    shows up in run_events like every other node on the canvas.
    """

    async def _handler(state: RunState) -> dict[str, Any]:
        ts = datetime.now(UTC)
        await _maybe_emit(event_emitter, state["step_index"], node_id, "node_start", {}, ts)
        await _maybe_emit(event_emitter, state["step_index"], node_id, "node_end", {}, ts)
        return {}

    return _handler


def make_loop_handler(
    node_id: str,
    expr: str,
    max_iterations: int,
    event_emitter: EventEmitter | None = None,
) -> NodeHandler:
    """Loop node: advances the checkpointed iteration counter and decides
    whether to continue into the loop body or exit.

    The decision is made here, not in a separate conditional-edge routing
    function, because only this handler sees the counter's value *before*
    this visit's own update. A routing function only sees the state *after*
    the handler ran, where "just performed the Nth body execution" and "max
    iterations was already reached, this visit only confirms exit" can both
    show the identical persisted counter value — there'd be no way for a
    route function to tell them apart. So the decision is computed here and
    written to loop_continue for GraphCompiler's route function to read
    directly, and loop_counters is only ever advanced when actually
    continuing into the body — it never exceeds max_iterations.

    Both loop_counters and loop_continue are plain RunState, checkpointed
    like every other field, so a crash mid-loop resumes with the same
    decision LangGraph would have made on first execution: re-enter this
    node fresh, read the checkpointed counter, recompute deterministically.
    """

    async def _handler(state: RunState) -> dict[str, Any]:
        ts = datetime.now(UTC)
        step = state["step_index"]
        await _maybe_emit(event_emitter, step, node_id, "node_start", {}, ts)

        current = state["loop_counters"].get(node_id, 0)
        capped = current >= max_iterations
        if capped:
            should_continue = False
        else:
            try:
                should_continue = evaluate_condition(expr, namespace_from_state(state))
            except ExprEvaluationError as exc:
                raise GraphCompilationError(
                    f"loop node '{node_id}' expr {expr!r} failed: {exc}"
                ) from exc

        new_count = current + 1 if should_continue else current
        if capped:
            await _maybe_emit(
                event_emitter,
                step,
                node_id,
                "node_end",
                {
                    "warning": "max_iterations reached, forcing exit",
                    "max_iterations": max_iterations,
                },
                ts,
            )
        else:
            await _maybe_emit(
                event_emitter, step, node_id, "node_end", {"iteration": new_count}, ts
            )

        return {
            "loop_counters": {**state["loop_counters"], node_id: new_count},
            "loop_continue": {**state["loop_continue"], node_id: should_continue},
            "step_index": step + 1,
        }

    return _handler


def make_output_handler(
    node_id: str = "output",
    event_emitter: EventEmitter | None = None,
) -> NodeHandler:
    """Output node: extracts the final assistant answer from messages."""

    async def _handler(state: RunState) -> dict[str, Any]:
        ts = datetime.now(UTC)
        step = state["step_index"]
        await _maybe_emit(event_emitter, step, node_id, "node_start", {}, ts)
        for msg in reversed(state["messages"]):
            if msg.get("role") == "assistant" and msg.get("content"):
                await _maybe_emit(
                    event_emitter,
                    step,
                    node_id,
                    "node_end",
                    {"output_preview": str(msg["content"])[:200]},
                    ts,
                )
                return {"output": msg["content"]}
        await _maybe_emit(event_emitter, step, node_id, "node_end", {}, ts)
        return {"output": None}

    return _handler
