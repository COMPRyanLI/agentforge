"""GraphCompiler: turns graph_json into a runnable LangGraph StateGraph.

Tool reference rules (two node types, two formats):
- llm node  data.tools     → list of tool NAMES  (e.g. ["calculator"])
- tool node data.tool_id   → UUID string; caller must pass tool_id_to_name map
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.llm.provider import LLMProvider
from app.runtime.errors import GraphCompilationError
from app.runtime.handlers import (
    NodeHandler,
    make_input_handler,
    make_llm_handler,
    make_output_handler,
    make_tool_handler,
)
from app.runtime.registry import ToolRegistry
from app.runtime.state import RunState

if TYPE_CHECKING:
    from app.runtime.event_emitter import EventEmitter


class GraphCompiler:
    """Compiles a graph_json dict into a LangGraph CompiledStateGraph."""

    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        tool_id_to_name: dict[str, str] | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        # Maps str(tool_uuid) → tool.name for standalone tool nodes
        self._tool_id_to_name: dict[str, str] = tool_id_to_name or {}
        self._event_emitter = event_emitter

    def compile(
        self, graph_json: dict[str, Any]
    ) -> CompiledStateGraph[RunState, RunState, RunState]:
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

        sg: StateGraph[RunState] = StateGraph(RunState)

        for node in nodes:
            handler = self._make_handler(node)
            # justified: LangGraph 1.2.5 add_node overloads require _Node[NodeInputT]
            # which doesn't recognise Callable[[TypedDict], Awaitable[dict]] directly.
            sg.add_node(node["id"], handler)  # type: ignore[call-overload]

        for edge in edges:
            sg.add_edge(edge["source"], edge["target"])

        entry_id: str = input_nodes[0]["id"]
        exit_id: str = output_nodes[0]["id"]
        sg.set_entry_point(entry_id)
        sg.add_edge(exit_id, END)

        return sg.compile()  # type: ignore[return-value]

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
                    node_id=node_id,
                    event_emitter=emitter,
                )
            case "tool":
                tool_id: str = str(data.get("tool_id") or "")
                tool_name = self._tool_id_to_name.get(tool_id, tool_id)
                return make_tool_handler(
                    self._registry, tool_name, node_id=node_id, event_emitter=emitter
                )
            case "output":
                return make_output_handler(node_id=node_id, event_emitter=emitter)
            case _:
                raise GraphCompilationError(f"Unknown node type: {node_type!r}")
