"""Each seeded template must compile and execute as a distinct runtime
pattern (chat, builtin-tool call, condition branching, bounded loop) — and
none of them may reference a DB-backed tool, since templates have no owner
to resolve one for (see app.runtime.registry_builder.graph_references_db_backed_tool,
the same gate app.services.agent.publish() uses)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.llm.provider import LLMProvider, LLMResponse
from app.runtime.builtins import register_builtins
from app.runtime.compiler import GraphCompiler
from app.runtime.registry import ToolRegistry
from app.runtime.registry_builder import graph_references_db_backed_tool
from app.runtime.state import RunState
from app.scripts.seed_templates import TEMPLATES
from tests.unit.runtime.conftest import dummy_session_factory


@pytest.fixture
def registry() -> ToolRegistry:
    r = ToolRegistry()
    register_builtins(r)
    return r


def _initial_state() -> RunState:
    return {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "messages": [{"role": "user", "content": "hello"}],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
        "loop_continue": {},
    }


def _template(name: str) -> dict[str, object]:
    for spec in TEMPLATES:
        if spec["name"] == name:
            return spec
    raise AssertionError(f"no seeded template named {name!r}")


@pytest.mark.parametrize("name", [spec["name"] for spec in TEMPLATES])
def test_no_template_references_a_db_backed_tool(name: str) -> None:
    spec = _template(name)
    assert graph_references_db_backed_tool(spec["graph_json"]) is False  # type: ignore[arg-type]


@pytest.mark.parametrize("name", [spec["name"] for spec in TEMPLATES])
def test_every_template_compiles(name: str, registry: ToolRegistry) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    c.compile(_template(name)["graph_json"])  # type: ignore[arg-type]


async def test_friendly_chatbot_executes_end_to_end(registry: ToolRegistry) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="Hi there!", tool_calls=[])  # type: ignore[attr-defined]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_template("Friendly Chatbot")["graph_json"])  # type: ignore[arg-type]

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "chatbot"}}
    )

    assert result["output"] == "Hi there!"


async def test_calculator_assistant_executes_end_to_end(registry: ToolRegistry) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="The answer is 4.", tool_calls=[])  # type: ignore[attr-defined]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_template("Calculator Assistant")["graph_json"])  # type: ignore[arg-type]

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "calc"}}
    )

    assert result["output"] == "The answer is 4."


async def test_triage_router_takes_urgent_branch(registry: ToolRegistry) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(content="URGENT", tool_calls=[]),
        LLMResponse(content="Escalating immediately.", tool_calls=[]),
    ]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_template("Triage Router")["graph_json"])  # type: ignore[arg-type]

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "triage-urgent"}}
    )

    assert result["output"] == "Escalating immediately."
    assert mock_llm.chat.call_count == 2  # type: ignore[attr-defined]


async def test_triage_router_takes_normal_branch(registry: ToolRegistry) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(content="NORMAL", tool_calls=[]),
        LLMResponse(content="Happy to help with that.", tool_calls=[]),
    ]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_template("Triage Router")["graph_json"])  # type: ignore[arg-type]

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "triage-normal"}}
    )

    assert result["output"] == "Happy to help with that."
    assert mock_llm.chat.call_count == 2  # type: ignore[attr-defined]


async def test_iterative_refiner_runs_exactly_max_iterations(registry: ToolRegistry) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="refined answer", tool_calls=[])  # type: ignore[attr-defined]
    c = GraphCompiler(mock_llm, registry, dummy_session_factory)
    compile_result = c.compile(_template("Iterative Refiner")["graph_json"])  # type: ignore[arg-type]

    result = await compile_result.graph.ainvoke(
        _initial_state(), {"configurable": {"thread_id": "refiner"}}
    )

    assert mock_llm.chat.call_count == 3  # type: ignore[attr-defined]
    assert result["loop_counters"]["loop"] == 3
    assert result["output"] == "refined answer"
