"""Unit tests for the loop node: iteration cap, recursion_limit sizing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.llm.provider import LLMProvider, LLMResponse
from app.runtime.builtins import register_builtins
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import GraphCompilationError
from app.runtime.executor import execute_graph
from app.runtime.registry import ToolRegistry
from app.runtime.state import RunState
from tests.unit.runtime.conftest import dummy_session_factory


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


def _loop_graph(max_iterations: int) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "in", "type": "input"},
            {
                "id": "loop",
                "type": "loop",
                "data": {"expr": "step_index >= 0", "max_iterations": max_iterations},
            },
            {"id": "llm1", "type": "llm", "data": {"system_prompt": "go", "tools": []}},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"source": "in", "target": "loop"},
            {"source": "loop", "target": "llm1", "condition": "true"},
            {"source": "loop", "target": "out", "condition": "false"},
            {"source": "llm1", "target": "loop"},
        ],
    }


def _initial_state() -> RunState:
    return {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "messages": [{"role": "user", "content": "go"}],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
        "loop_continue": {},
    }


async def test_loop_runs_exactly_max_iterations_then_exits(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_loop_graph(max_iterations=3))

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "loop1"}}
    )

    assert mock_llm.chat.call_count == 3  # type: ignore[attr-defined]
    assert result["output"] == "ok"
    # Counter never exceeds max_iterations: the forced-exit visit confirms
    # exit without advancing the counter past the cap.
    assert result["loop_counters"]["loop"] == 3


@pytest.mark.parametrize("max_iterations", [1, 3, 5])
async def test_loop_counter_and_events_never_exceed_max_iterations(
    max_iterations: int, mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    """expr is always true, so only the max_iterations cap bounds the loop.

    Asserts the EXACT body-execution count for each max_iterations (not just
    that a forced-exit warning eventually appears), and that no node_end
    event for the loop node ever reports an iteration number greater than
    max_iterations.
    """
    emitter = AsyncMock()
    c = GraphCompiler(mock_llm, registry, dummy_session_factory, event_emitter=emitter)
    compile_result = c.compile(_loop_graph(max_iterations=max_iterations))

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": f"loop-cap-{max_iterations}"}}
    )

    assert mock_llm.chat.call_count == max_iterations  # type: ignore[attr-defined]
    assert result["loop_counters"]["loop"] == max_iterations

    iteration_numbers = [
        call.kwargs["payload"]["iteration"]
        for call in emitter.emit.call_args_list
        if call.kwargs.get("node_id") == "loop" and "iteration" in call.kwargs["payload"]
    ]
    assert iteration_numbers == list(range(1, max_iterations + 1))
    assert all(n <= max_iterations for n in iteration_numbers)


async def test_loop_forced_exit_ignores_always_true_expr(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    """expr is always true; only max_iterations bounds the loop."""
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_loop_graph(max_iterations=1))

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "loop2"}}
    )

    assert mock_llm.chat.call_count == 1  # type: ignore[attr-defined]
    assert result["output"] == "ok"


def test_loop_node_missing_max_iterations_raises(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    graph = _loop_graph(max_iterations=1)
    del graph["nodes"][1]["data"]["max_iterations"]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    with pytest.raises(GraphCompilationError, match="max_iterations"):
        c.compile(graph)


def test_loop_node_zero_max_iterations_raises(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    with pytest.raises(GraphCompilationError, match="max_iterations must be >= 1"):
        c.compile(_loop_graph(max_iterations=0))


def test_nested_loop_node_raises(mock_llm: LLMProvider, registry: ToolRegistry) -> None:
    """An inner loop node's loop_counters never resets across outer
    iterations, so it would silently run far fewer iterations than declared
    rather than erroring — reject nesting at compile time instead."""
    graph: dict[str, Any] = {
        "nodes": [
            {"id": "in", "type": "input"},
            {
                "id": "outer",
                "type": "loop",
                "data": {"expr": "step_index >= 0", "max_iterations": 3},
            },
            {
                "id": "inner",
                "type": "loop",
                "data": {"expr": "step_index >= 0", "max_iterations": 5},
            },
            {"id": "llm1", "type": "llm", "data": {"system_prompt": "go", "tools": []}},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"source": "in", "target": "outer"},
            {"source": "outer", "target": "inner", "condition": "true"},
            {"source": "outer", "target": "out", "condition": "false"},
            {"source": "inner", "target": "llm1", "condition": "true"},
            {"source": "inner", "target": "outer", "condition": "false"},
            {"source": "llm1", "target": "inner"},
        ],
    }
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    with pytest.raises(GraphCompilationError, match="nested"):
        c.compile(graph)


async def test_recursion_limit_sized_above_langgraph_default(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    """30 iterations would blow LangGraph's default recursion_limit (25)
    without GraphCompiler computing and wiring through a larger one."""
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_loop_graph(max_iterations=30))
    assert compile_result.recursion_limit > 25

    result = await execute_graph(
        compile_result.graph,
        run_id="r1",
        thread_id="loop-recursion",
        user_input="go",
        recursion_limit=compile_result.recursion_limit,
    )
    assert result.output == "ok"
    assert mock_llm.chat.call_count == 30  # type: ignore[attr-defined]


async def test_undersized_recursion_limit_raises(
    mock_llm: LLMProvider, registry: ToolRegistry
) -> None:
    """Proves the computed recursion_limit is load-bearing, not redundant:
    the same 30-iteration loop fails under a limit too small for it (the
    LangGraph default itself is version/env-configurable — see
    GraphCompiler._compute_recursion_limit's docstring — so this pins the
    point to an explicit too-small value rather than depending on whatever
    the installed LangGraph version's default happens to be)."""
    from langgraph.errors import GraphRecursionError

    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_loop_graph(max_iterations=30))
    assert compile_result.recursion_limit > 25

    with pytest.raises(GraphRecursionError):
        await execute_graph(
            compile_result.graph,
            run_id="r2",
            thread_id="loop-recursion-2",
            user_input="go",
            recursion_limit=25,
        )
