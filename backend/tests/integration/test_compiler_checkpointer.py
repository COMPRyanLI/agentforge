"""Integration test: GraphCompiler attaches a real Postgres checkpointer.

Verifies the core mechanic resume/replay depend on: invoking a checkpointed
graph a second time with `ainvoke(None, config)` on the same thread_id
continues from the last checkpoint instead of re-running already-completed
nodes (and, for the llm node, without re-calling the LLM).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.llm.provider import LLMProvider, LLMResponse
from app.runtime.builtins import register_builtins
from app.runtime.checkpointer import _to_psycopg_dsn
from app.runtime.compiler import GraphCompiler
from app.runtime.registry import ToolRegistry
from app.runtime.state import RunState
from tests.unit.runtime.conftest import dummy_session_factory

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


@pytest.fixture
async def saver(db_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    dsn = _to_psycopg_dsn(db_url)
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        dsn,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    s = AsyncPostgresSaver(pool)
    await s.setup()
    yield s
    await pool.close()


async def test_second_ainvoke_on_same_thread_does_not_recall_llm(
    saver: AsyncPostgresSaver,
) -> None:
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="Hello!", tool_calls=[])  # type: ignore[attr-defined]

    registry = ToolRegistry()
    register_builtins(registry)

    compiled = GraphCompiler(mock_llm, registry, dummy_session_factory, checkpointer=saver).compile(
        LLM_GRAPH
    )

    thread_id = "checkpointed-thread"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    initial: RunState = {
        "run_id": "r1",
        "messages": [{"role": "user", "content": "hi"}],
        "output": None,
        "step_index": 0,
        "error": None,
    }

    result = await compiled.ainvoke(initial, config)
    assert result["output"] == "Hello!"
    assert mock_llm.chat.call_count == 1  # type: ignore[attr-defined]

    # The graph already reached its finish point, so a second ainvoke(None, ...)
    # on the same thread_id has nothing left to resume — it should return the
    # already-checkpointed final state without invoking any node (and
    # therefore without calling the LLM again).
    resumed = await compiled.ainvoke(None, config)
    assert resumed["output"] == "Hello!"
    assert mock_llm.chat.call_count == 1  # type: ignore[attr-defined]
