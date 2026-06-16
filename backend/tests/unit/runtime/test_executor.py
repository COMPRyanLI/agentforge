"""Unit tests for execute_graph."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.llm.provider import LLMProvider, LLMResponse
from app.runtime.builtins import register_builtins
from app.runtime.compiler import GraphCompiler
from app.runtime.executor import execute_graph
from app.runtime.registry import ToolRegistry

SIMPLE_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "llm1", "type": "llm", "data": {"system_prompt": "Be brief.", "tools": []}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "out"},
    ],
}


@pytest.fixture
def mock_llm() -> LLMProvider:
    m: LLMProvider = AsyncMock(spec=LLMProvider)
    m.chat.return_value = LLMResponse(content="The answer is 42.", tool_calls=[])  # type: ignore[attr-defined]
    return m


@pytest.fixture
def compiled_graph(mock_llm: LLMProvider) -> Any:
    registry = ToolRegistry()
    register_builtins(registry)
    return GraphCompiler(mock_llm, registry).compile(SIMPLE_GRAPH)


async def test_execute_graph_returns_output(compiled_graph: Any, mock_llm: LLMProvider) -> None:
    output = await execute_graph(
        compiled_graph,
        run_id="run-1",
        thread_id="thread-1",
        user_input="what is the answer?",
    )
    assert output == "The answer is 42."


async def test_execute_graph_timeout_raises(mock_llm: LLMProvider) -> None:
    registry = ToolRegistry()
    register_builtins(registry)

    # Make the LLM call hang forever
    async def _hang(messages: Any, tools: Any = None) -> Any:
        await asyncio.sleep(9999)

    mock_llm.chat.side_effect = _hang  # type: ignore[attr-defined]
    cg = GraphCompiler(mock_llm, registry).compile(SIMPLE_GRAPH)

    with pytest.raises(TimeoutError):
        await execute_graph(
            cg,
            run_id="run-2",
            thread_id="thread-2",
            user_input="hi",
            deadline=0.01,
        )
