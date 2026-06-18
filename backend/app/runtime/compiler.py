"""GraphCompiler: turns graph_json into a runnable LangGraph StateGraph.

Tool reference rules (two node types, two formats):
- llm node  data.tools     → list of tool NAMES  (e.g. ["calculator"])
- tool node data.tool_id   → UUID string; caller must pass tool_id_to_name map

Branching rule: only `condition` and `loop` nodes may have more than one
outgoing edge. Their edges must each carry edge["condition"] == "true" or
"false" and are wired via LangGraph's add_conditional_edges, routed by
safely evaluating data.expr (app.runtime.expr) against the live RunState.
Every other node type may have at most one outgoing edge.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import LLMProvider
from app.runtime.errors import GraphCompilationError
from app.runtime.expr import ExprEvaluationError, evaluate_condition, namespace_from_state
from app.runtime.handlers import (
    make_condition_handler,
    make_input_handler,
    make_llm_handler,
    make_loop_handler,
    make_output_handler,
    make_tool_handler,
)
from app.runtime.registry import ToolRegistry
from app.runtime.retry import RetryPolicy, with_retry
from app.runtime.state import NodeHandler, RunState

if TYPE_CHECKING:
    from app.runtime.event_emitter import EventEmitter

# Node types whose outgoing edges are routed by add_conditional_edges instead
# of a static add_edge.
BRANCHING_NODE_TYPES = frozenset({"condition", "loop"})

# Extra super-steps of headroom added on top of the computed loop budget, to
# absorb retry-wrapped re-entries and the input/output bookend nodes without
# needing an exact step-counting model of LangGraph's internals.
_RECURSION_LIMIT_SLACK = 10


@dataclass(slots=True, frozen=True)
class CompileResult:
    # justified: CompiledStateGraph's 4th (ContextT) type param has no analogue
    # in this codebase's compile() call — Any matches the pre-existing
    # ignore[return-value] this replaces.
    graph: CompiledStateGraph[RunState, Any, RunState, RunState]
    # Must be passed to execute_graph's recursion_limit — LangGraph's own
    # default (25) is sized for loop-free graphs and will raise
    # GraphRecursionError on a legitimate multi-iteration loop otherwise.
    recursion_limit: int


class GraphCompiler:
    """Compiles a graph_json dict into a LangGraph CompiledStateGraph."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        session_factory: async_sessionmaker[AsyncSession],
        tool_id_to_name: dict[str, str] | None = None,
        event_emitter: EventEmitter | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._session_factory = session_factory
        # Maps str(tool_uuid) → tool.name for standalone tool nodes
        self._tool_id_to_name: dict[str, str] = tool_id_to_name or {}
        self._event_emitter = event_emitter
        self._checkpointer = checkpointer

    def compile(self, graph_json: dict[str, Any]) -> CompileResult:
        nodes: list[dict[str, Any]] = graph_json.get("nodes", [])
        edges: list[dict[str, Any]] = graph_json.get("edges", [])

        if not nodes:
            raise GraphCompilationError("graph_json has no nodes")

        input_nodes = [n for n in nodes if n.get("type") == "input"]
        output_nodes = [n for n in nodes if n.get("type") == "output"]
        if len(input_nodes) != 1:
            raise GraphCompilationError(
                f"graph_json must have exactly one 'input' node, found {len(input_nodes)}"
            )
        if len(output_nodes) != 1:
            raise GraphCompilationError(
                f"graph_json must have exactly one 'output' node, found {len(output_nodes)}"
            )

        node_type_by_id: dict[str, str] = {n["id"]: n.get("type", "") for n in nodes}
        self._validate_no_unguarded_cycles(node_type_by_id, edges)

        edges_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            edges_by_source[edge["source"]].append(edge)
        self._validate_loop_nodes_have_max_iterations(nodes, node_type_by_id, edges_by_source)

        sg: StateGraph[RunState] = StateGraph(RunState)

        for node in nodes:
            node_id: str = node.get("id", node.get("type", ""))
            handler = self._make_handler(node)
            # The llm node retries its own individual llm.chat()/tool calls
            # internally (see make_llm_handler) — wrapping its whole node here
            # too would re-issue already-completed LLM calls on a tool retry.
            if node.get("type") != "llm":
                handler = with_retry(
                    handler, node_id, self._retry_policy(node), self._event_emitter
                )
            # justified: LangGraph 1.2.5 add_node overloads require _Node[NodeInputT]
            # which doesn't recognise Callable[[TypedDict], Awaitable[dict]] directly.
            sg.add_node(node["id"], handler)  # type: ignore[call-overload]

        for node in nodes:
            node_id = node["id"]
            node_type = node.get("type", "")
            outgoing = edges_by_source.get(node_id, [])
            if node_type in BRANCHING_NODE_TYPES:
                sg.add_conditional_edges(
                    node_id,
                    self._make_route_fn(node, outgoing),
                    cast("dict[Hashable, str]", self._branch_targets(node_id, node_type, outgoing)),
                )
            else:
                if len(outgoing) > 1:
                    raise GraphCompilationError(
                        f"Node '{node_id}' (type {node_type!r}) has {len(outgoing)} "
                        "outgoing edges; only condition/loop nodes may branch"
                    )
                for edge in outgoing:
                    sg.add_edge(node_id, edge["target"])

        entry_id: str = input_nodes[0]["id"]
        exit_id: str = output_nodes[0]["id"]
        sg.set_entry_point(entry_id)
        sg.add_edge(exit_id, END)

        compiled = sg.compile(checkpointer=self._checkpointer)
        recursion_limit = self._compute_recursion_limit(nodes, node_type_by_id, edges_by_source)
        return CompileResult(graph=compiled, recursion_limit=recursion_limit)

    def _compute_recursion_limit(
        self,
        nodes: list[dict[str, Any]],
        node_type_by_id: dict[str, str],
        edges_by_source: dict[str, list[dict[str, Any]]],
    ) -> int:
        """Size LangGraph's recursion_limit from the graph's loop node(s).

        LangGraph's own default recursion_limit has no relationship to a
        loop node's max_iterations — relying on the library default to catch
        a runaway loop means the actual bound is whatever that default happens
        to be (it's overridable via an environment variable, so it isn't even
        a fixed number), not the cap the graph author actually declared. This
        computes an explicit limit tied to max_iterations instead. Each loop
        node tick (the loop node's own re-entry, not just its body) counts as
        one super-step, so the budget per loop node is
        max_iterations * (body_width + 1) — the +1 is the loop node's own
        per-iteration tick, body_width is the nodes reachable from the loop's
        "true" edge before control returns to the loop node — plus one step
        per node outside any loop, plus slack for the bookend ticks.
        """
        limit = len(nodes) + _RECURSION_LIMIT_SLACK
        for node in nodes:
            if node_type_by_id.get(node["id"]) != "loop":
                continue
            data: dict[str, Any] = node.get("data") or {}
            max_iterations = int(data.get("max_iterations", 1))
            body_width = max(1, self._loop_body_width(node["id"], edges_by_source)) + 1
            limit += max_iterations * body_width
        return limit

    def _loop_body_width(
        self, loop_node_id: str, edges_by_source: dict[str, list[dict[str, Any]]]
    ) -> int:
        """Count nodes reachable from a loop node's "true" edge, stopping at
        the edge back to the loop node itself — an upper bound on how many
        node executions one loop iteration costs."""
        true_target: str | None = None
        for edge in edges_by_source.get(loop_node_id, []):
            if edge.get("condition") == "true":
                true_target = edge["target"]
        if true_target is None:
            return 0
        visited: set[str] = set()
        stack = [true_target]
        while stack:
            node_id = stack.pop()
            if node_id in visited or node_id == loop_node_id:
                continue
            visited.add(node_id)
            for edge in edges_by_source.get(node_id, []):
                stack.append(edge["target"])
        return len(visited)

    def _branch_targets(
        self, node_id: str, node_type: str, outgoing: list[dict[str, Any]]
    ) -> dict[str, str]:
        tagged: dict[str, str] = {}
        for edge in outgoing:
            tag = edge.get("condition")
            if tag not in ("true", "false"):
                raise GraphCompilationError(
                    f"{node_type} node '{node_id}' outgoing edge must have "
                    f"condition 'true' or 'false', got {tag!r}"
                )
            if tag in tagged:
                raise GraphCompilationError(
                    f"{node_type} node '{node_id}' has more than one {tag!r} edge"
                )
            tagged[tag] = edge["target"]
        if set(tagged) != {"true", "false"}:
            raise GraphCompilationError(
                f"{node_type} node '{node_id}' must have exactly one 'true' and "
                f"one 'false' outgoing edge, got {sorted(tagged)}"
            )
        return tagged

    def _make_route_fn(self, node: dict[str, Any], outgoing: list[dict[str, Any]]) -> Any:
        node_type = node.get("type", "")
        data: dict[str, Any] = node.get("data") or {}
        expr = str(data.get("expr") or "")
        node_id = node["id"]

        def _eval_expr(state: RunState) -> bool:
            try:
                return evaluate_condition(expr, namespace_from_state(state))
            except ExprEvaluationError as exc:
                raise GraphCompilationError(
                    f"{node_type} node '{node_id}' expr {expr!r} failed: {exc}"
                ) from exc

        if node_type == "loop":
            max_iterations = int(data.get("max_iterations", 1))
            emitter = self._event_emitter

            async def _route_loop(state: RunState) -> str:
                # count is incremented by make_loop_handler before this route
                # function runs, so count == "how many times has the loop body
                # been offered so far"; allowing through while count <= max_iterations
                # (not <) makes exactly max_iterations body executions happen.
                count = state["loop_counters"].get(node_id, 0)
                if count > max_iterations:
                    if emitter is not None:
                        await emitter.emit(
                            step_index=state["step_index"],
                            node_id=node_id,
                            event_type="retry",
                            payload={
                                "warning": "max_iterations reached, forcing exit",
                                "max_iterations": max_iterations,
                            },
                            ts=datetime.now(UTC),
                        )
                    return "false"
                return "true" if _eval_expr(state) else "false"

            return _route_loop

        async def _route(state: RunState) -> str:
            return "true" if _eval_expr(state) else "false"

        return _route

    def _validate_loop_nodes_have_max_iterations(
        self,
        nodes: list[dict[str, Any]],
        node_type_by_id: dict[str, str],
        edges_by_source: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Every loop node must declare a positive integer max_iterations.

        This is the hard cap against runaway loops (CLAUDE.md's "bounded
        iteration" requirement) — without it a loop node would default to 1
        iteration silently, which is a correctness footgun, not a safe default.
        """
        for node in nodes:
            if node_type_by_id.get(node["id"]) != "loop":
                continue
            data: dict[str, Any] = node.get("data") or {}
            max_iterations = data.get("max_iterations")
            if not isinstance(max_iterations, int) or isinstance(max_iterations, bool):
                raise GraphCompilationError(
                    f"loop node '{node['id']}' must declare an integer data.max_iterations"
                )
            if max_iterations < 1:
                raise GraphCompilationError(
                    f"loop node '{node['id']}' max_iterations must be >= 1, got {max_iterations}"
                )

    def _validate_no_unguarded_cycles(
        self, node_type_by_id: dict[str, str], edges: list[dict[str, Any]]
    ) -> None:
        """Reject any cycle in the edge graph that doesn't pass through a 'loop' node.

        A cycle through only condition/llm/tool nodes has no iteration cap and
        no checkpointed counter — it would either loop forever or rely on
        LangGraph's recursion limit as an accidental, unconfigurable guard.
        Enforced here (not just in the frontend validator) so a client that
        bypasses the canvas's validation still can't compile such a graph.
        """
        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge["source"]].append(edge["target"])

        visited: set[str] = set()
        on_stack: list[str] = []
        on_stack_set: set[str] = set()

        def dfs(node_id: str) -> None:
            visited.add(node_id)
            on_stack.append(node_id)
            on_stack_set.add(node_id)
            for target in adjacency.get(node_id, []):
                if target in on_stack_set:
                    cycle_start = on_stack.index(target)
                    cycle_nodes = on_stack[cycle_start:]
                    if not any(node_type_by_id.get(n) == "loop" for n in cycle_nodes):
                        raise GraphCompilationError(
                            f"Cycle {cycle_nodes!r} does not pass through a 'loop' node"
                        )
                elif target not in visited:
                    dfs(target)
            on_stack.pop()
            on_stack_set.remove(node_id)

        for node_id in node_type_by_id:
            if node_id not in visited:
                dfs(node_id)

    def _retry_policy(self, node: dict[str, Any]) -> RetryPolicy:
        data: dict[str, Any] = node.get("data") or {}
        retry_data: dict[str, Any] = data.get("retry") or {}
        kwargs: dict[str, Any] = {}
        if "max_retries" in retry_data:
            kwargs["max_retries"] = int(retry_data["max_retries"])
        if "backoff_seconds" in retry_data:
            kwargs["base_backoff_seconds"] = float(retry_data["backoff_seconds"])
        return RetryPolicy(**kwargs)

    def _make_handler(self, node: dict[str, Any]) -> NodeHandler:
        node_type: str = node.get("type", "")
        node_id: str = node.get("id", node_type)
        data: dict[str, Any] = node.get("data") or {}
        emitter = self._event_emitter

        match node_type:
            case "input":
                return make_input_handler(node_id=node_id, event_emitter=emitter)
            case "llm":
                return make_llm_handler(
                    llm=self._llm,
                    registry=self._registry,
                    tool_names=list(data.get("tools") or []),
                    system_prompt=str(data.get("system_prompt") or "You are a helpful assistant."),
                    session_factory=self._session_factory,
                    retry_policy=self._retry_policy(node),
                    node_id=node_id,
                    event_emitter=emitter,
                )
            case "tool":
                tool_id: str = str(data.get("tool_id") or "")
                tool_name = self._tool_id_to_name.get(tool_id, tool_id)
                return make_tool_handler(
                    self._registry,
                    tool_name,
                    self._session_factory,
                    node_id=node_id,
                    event_emitter=emitter,
                    require_approval=bool(data.get("require_approval", False)),
                )
            case "condition":
                return make_condition_handler(node_id=node_id, event_emitter=emitter)
            case "loop":
                return make_loop_handler(node_id=node_id, event_emitter=emitter)
            case "output":
                return make_output_handler(node_id=node_id, event_emitter=emitter)
            case _:
                raise GraphCompilationError(f"Unknown node type: {node_type!r}")
