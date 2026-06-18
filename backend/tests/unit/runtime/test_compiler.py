"""Unit tests for GraphCompiler."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.llm.provider import LLMProvider, LLMResponse
from app.runtime.builtins import register_builtins
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import GraphCompilationError
from app.runtime.registry import ToolRegistry
from tests.unit.runtime.conftest import FakeToolCallRepo, dummy_session_factory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    register_builtins(r)
    return r


@pytest.fixture
def mock_llm() -> LLMProvider:
    m: LLMProvider = AsyncMock(spec=LLMProvider)
    m.chat.return_value = LLMResponse(content="ok", tool_calls=[])  # type: ignore[attr-defined]
    return m


@pytest.fixture
def compiler(mock_llm: LLMProvider, registry: ToolRegistry) -> GraphCompiler:
    return GraphCompiler(llm=mock_llm, registry=registry, session_factory=dummy_session_factory)


# ---------------------------------------------------------------------------
# Minimal graphs
# ---------------------------------------------------------------------------

MINIMAL_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "out", "type": "output"},
    ],
    "edges": [{"source": "in", "target": "out"}],
}


def test_compile_minimal_graph(compiler: GraphCompiler) -> None:
    compiled = compiler.compile(MINIMAL_GRAPH)
    assert compiled is not None


async def test_compile_and_invoke_minimal(compiler: GraphCompiler) -> None:
    compiled = compiler.compile(MINIMAL_GRAPH).graph
    from app.runtime.state import RunState

    initial: RunState = {
        "run_id": "r1",
        "messages": [{"role": "user", "content": "hi"}],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
    }
    result = await compiled.ainvoke(initial, {"configurable": {"thread_id": "t1"}})
    # output node looks for assistant message; there is none → output=None
    assert result["output"] is None


# ---------------------------------------------------------------------------
# Full graph with LLM node
# ---------------------------------------------------------------------------

LLM_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "llm1", "type": "llm", "data": {"system_prompt": "Be concise.", "tools": []}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "out"},
    ],
}


async def test_compile_llm_graph_returns_output(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    mock_llm.chat.return_value = LLMResponse(content="Hello!", tool_calls=[])  # type: ignore[attr-defined]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory).compile(LLM_GRAPH).graph
    from app.runtime.state import RunState

    state: RunState = {
        "run_id": "r1",
        "messages": [{"role": "user", "content": "hi"}],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
    }
    result = await c.ainvoke(state, {"configurable": {"thread_id": "t2"}})
    assert result["output"] == "Hello!"


# ---------------------------------------------------------------------------
# Tool node
# ---------------------------------------------------------------------------

TOOL_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "t1", "type": "tool", "data": {"tool_id": "calc-uuid"}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "t1"},
        {"source": "t1", "target": "out"},
    ],
}


def test_compile_tool_node_with_id_mapping(mock_llm: LLMProvider, registry: ToolRegistry) -> None:
    c = GraphCompiler(
        mock_llm, registry, dummy_session_factory, tool_id_to_name={"calc-uuid": "calculator"}
    )
    compiled = c.compile(TOOL_GRAPH)
    assert compiled is not None


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_compile_empty_nodes_raises(compiler: GraphCompiler) -> None:
    with pytest.raises(GraphCompilationError, match="no nodes"):
        compiler.compile({"nodes": [], "edges": []})


def test_compile_missing_input_node_raises(compiler: GraphCompiler) -> None:
    with pytest.raises(GraphCompilationError, match="input"):
        compiler.compile(
            {
                "nodes": [{"id": "out", "type": "output"}],
                "edges": [],
            }
        )


def test_compile_missing_output_node_raises(compiler: GraphCompiler) -> None:
    with pytest.raises(GraphCompilationError, match="output"):
        compiler.compile(
            {
                "nodes": [{"id": "in", "type": "input"}],
                "edges": [],
            }
        )


def test_compile_unknown_node_type_raises(compiler: GraphCompiler) -> None:
    with pytest.raises(GraphCompilationError, match="Unknown node type"):
        compiler.compile(
            {
                "nodes": [
                    {"id": "in", "type": "input"},
                    {"id": "bad", "type": "wizard"},
                    {"id": "out", "type": "output"},
                ],
                "edges": [
                    {"source": "in", "target": "bad"},
                    {"source": "bad", "target": "out"},
                ],
            }
        )


def test_compile_multiple_input_nodes_raises(compiler: GraphCompiler) -> None:
    with pytest.raises(GraphCompilationError, match="exactly one 'input'"):
        compiler.compile(
            {
                "nodes": [
                    {"id": "in1", "type": "input"},
                    {"id": "in2", "type": "input"},
                    {"id": "out", "type": "output"},
                ],
                "edges": [],
            }
        )


# ---------------------------------------------------------------------------
# Condition node
# ---------------------------------------------------------------------------

CONDITION_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {
            "id": "cond",
            "type": "condition",
            "data": {"expr": "last_tool_result == 5"},
        },
        {"id": "t1", "type": "tool", "data": {"tool_id": "calc-uuid"}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "cond"},
        {"source": "cond", "target": "t1", "condition": "true"},
        {"source": "cond", "target": "out", "condition": "false"},
        {"source": "t1", "target": "out"},
    ],
}


def test_compile_condition_graph(mock_llm: LLMProvider, registry: ToolRegistry) -> None:
    c = GraphCompiler(
        mock_llm, registry, dummy_session_factory, tool_id_to_name={"calc-uuid": "calculator"}
    )
    compiled = c.compile(CONDITION_GRAPH)
    assert compiled is not None


async def test_condition_routes_true(
    mock_llm: LLMProvider, registry: ToolRegistry, fake_tool_call_repo: FakeToolCallRepo
) -> None:
    from app.runtime.state import RunState

    c = GraphCompiler(
        mock_llm, registry, dummy_session_factory, tool_id_to_name={"calc-uuid": "calculator"}
    )
    compiled = c.compile(CONDITION_GRAPH).graph
    state: RunState = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": {"expression": "2+3"}}}
                ],
            },
            {"role": "tool", "name": "calculator", "content": "5"},
        ],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
    }
    result = await compiled.ainvoke(state, {"configurable": {"thread_id": "tcond1"}})
    # condition is true (last_tool_result == 5) -> routes through the tool node,
    # which increments step_index; the false branch goes straight to output
    # without touching step_index (see make_condition_handler/make_output_handler).
    assert result["step_index"] == 1


async def test_condition_routes_false(mock_llm: LLMProvider, registry: ToolRegistry) -> None:
    from app.runtime.state import RunState

    c = GraphCompiler(
        mock_llm, registry, dummy_session_factory, tool_id_to_name={"calc-uuid": "calculator"}
    )
    compiled = c.compile(CONDITION_GRAPH).graph
    state: RunState = {
        "run_id": "r1",
        "messages": [{"role": "user", "content": "hi"}],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
    }
    result = await compiled.ainvoke(state, {"configurable": {"thread_id": "tcond2"}})
    # last_tool_result is None -> "None == 5" is false -> routes straight to
    # output, never touching the tool node, so step_index stays 0.
    assert result["step_index"] == 0


def test_condition_node_missing_condition_tag_raises(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    with pytest.raises(GraphCompilationError, match="condition 'true' or 'false'"):
        c.compile(
            {
                "nodes": [
                    {"id": "in", "type": "input"},
                    {"id": "cond", "type": "condition", "data": {"expr": "step_index == 0"}},
                    {"id": "out", "type": "output"},
                ],
                "edges": [
                    {"source": "in", "target": "cond"},
                    {"source": "cond", "target": "out"},
                ],
            }
        )


def test_non_branching_node_with_multiple_outgoing_edges_raises(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    c = GraphCompiler(
        mock_llm, registry, dummy_session_factory, tool_id_to_name={"calc-uuid": "calculator"}
    )
    with pytest.raises(GraphCompilationError, match="only condition/loop nodes may branch"):
        c.compile(
            {
                "nodes": [
                    {"id": "in", "type": "input"},
                    {"id": "t1", "type": "tool", "data": {"tool_id": "calc-uuid"}},
                    {"id": "out1", "type": "output"},
                ],
                "edges": [
                    {"source": "in", "target": "t1"},
                    {"source": "t1", "target": "out1"},
                    {"source": "in", "target": "out1"},
                ],
            }
        )


def test_cycle_without_loop_node_raises(mock_llm: LLMProvider, registry: ToolRegistry) -> None:
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    with pytest.raises(GraphCompilationError, match="does not pass through a 'loop' node"):
        c.compile(
            {
                "nodes": [
                    {"id": "in", "type": "input"},
                    {"id": "cond", "type": "condition", "data": {"expr": "step_index < 3"}},
                    {"id": "out", "type": "output"},
                ],
                "edges": [
                    {"source": "in", "target": "cond"},
                    {"source": "cond", "target": "in", "condition": "true"},
                    {"source": "cond", "target": "out", "condition": "false"},
                ],
            }
        )
