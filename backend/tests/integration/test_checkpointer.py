"""Integration tests for app.runtime.checkpointer against a real Postgres."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.runtime.checkpointer import _to_psycopg_dsn, fork_thread_at_step
from app.runtime.state import RunState


async def _node_a(state: RunState) -> dict[str, Any]:
    return {"step_index": state["step_index"] + 1, "output": "a"}


async def _node_b(state: RunState) -> dict[str, Any]:
    return {"step_index": state["step_index"] + 1, "output": "b"}


def _build_graph() -> Any:
    sg = StateGraph(RunState)
    sg.add_node("a", _node_a)
    sg.add_node("b", _node_b)
    sg.set_entry_point("a")
    sg.add_edge("a", "b")
    sg.set_finish_point("b")
    return sg


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


async def test_fork_thread_at_step_copies_matching_checkpoint(
    saver: AsyncPostgresSaver,
) -> None:
    graph = _build_graph().compile(checkpointer=saver)
    old_thread_id = "old-thread"
    old_config: RunnableConfig = {"configurable": {"thread_id": old_thread_id}}

    result = await graph.ainvoke(
        {"run_id": "r1", "messages": [], "output": None, "step_index": 0, "error": None},
        old_config,
    )
    assert result["output"] == "b"
    assert result["step_index"] == 2

    new_thread_id = "new-thread"
    found = await fork_thread_at_step(saver, old_thread_id, new_thread_id, target_step_index=1)
    assert found is True

    new_config: RunnableConfig = {"configurable": {"thread_id": new_thread_id}}
    snapshot = await graph.aget_state(new_config)
    assert snapshot.values["step_index"] == 1
    assert snapshot.values["output"] == "a"

    # resuming the forked thread should continue forward from node "b" only
    resumed = await graph.ainvoke(None, new_config)
    assert resumed["output"] == "b"
    assert resumed["step_index"] == 2


async def test_fork_thread_at_step_returns_false_when_no_match(
    saver: AsyncPostgresSaver,
) -> None:
    graph = _build_graph().compile(checkpointer=saver)
    old_thread_id = "old-thread-2"
    old_config: RunnableConfig = {"configurable": {"thread_id": old_thread_id}}
    await graph.ainvoke(
        {"run_id": "r2", "messages": [], "output": None, "step_index": 0, "error": None},
        old_config,
    )

    found = await fork_thread_at_step(saver, old_thread_id, "new-thread-2", target_step_index=99)
    assert found is False
