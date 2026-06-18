"""GraphCompiler: turns graph_json into a runnable LangGraph StateGraph.

Tool reference rules (two node types, two formats):
- llm node  data.tools     → list of tool NAMES  (e.g. ["calculator"])
- tool node data.tool_id   → UUID string; caller must pass tool_id_to_name map
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import LLMProvider
from app.runtime.errors import GraphCompilationError
from app.runtime.handlers import (
    make_input_handler,
    make_llm_handler,
    make_output_handler,
    make_tool_handler,
)
from app.runtime.registry import ToolRegistry
from app.runtime.retry import RetryPolicy, with_retry
from app.runtime.state import NodeHandler, RunState

if TYPE_CHECKING:
    from app.runtime.event_emitter import EventEmitter


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

        for edge in edges:
            sg.add_edge(edge["source"], edge["target"])

        entry_id: str = input_nodes[0]["id"]
        exit_id: str = output_nodes[0]["id"]
        sg.set_entry_point(entry_id)
        sg.add_edge(exit_id, END)

        return sg.compile(checkpointer=self._checkpointer)  # type: ignore[return-value]

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
            case "output":
                return make_output_handler(node_id=node_id, event_emitter=emitter)
            case _:
                raise GraphCompilationError(f"Unknown node type: {node_type!r}")
