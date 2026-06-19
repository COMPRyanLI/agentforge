"""Integration tests for the require_approval human-in-the-loop tool flag.

Exercises the real interrupt()/Command(resume=...) mechanism against a real
Postgres checkpointer — mirrors the existing input->tool->output graph shape
already used by test_compiler.py's TOOL_GRAPH (a tool node doesn't need an
upstream llm node; it reads tool_calls directly from message history).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import LLMProvider
from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.user import User
from app.runtime.builtins import register_builtins
from app.runtime.checkpointer import _to_psycopg_dsn
from app.runtime.compiler import GraphCompiler
from app.runtime.errors import AgentRuntimeError
from app.runtime.registry import ToolRegistry
from app.runtime.state import RunState

APPROVAL_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {
            "id": "t1",
            "type": "tool",
            "data": {"tool_id": "calc", "require_approval": True},
        },
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "t1"},
        {"source": "t1", "target": "out"},
    ],
}


def _seed_state_with_pending_tool_call(run_id: str) -> RunState:
    return {
        "run_id": run_id,
        "messages": [
            {"role": "user", "content": "please run the calculation"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"function": {"name": "calculator", "arguments": {"expression": "1+1"}}}
                ],
            },
        ],
        "output": None,
        "step_index": 0,
        "error": None,
        "loop_counters": {},
        "loop_continue": {},
    }


async def _seed_run_id(session: AsyncSession) -> str:
    """tool_calls.run_id has a real FK to runs.id — seed a row so inserts succeed."""
    user = User(email=f"hitl_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()

    agent = Agent(owner_id=user.id, name="hitl-test-agent")
    session.add(agent)
    await session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json=APPROVAL_GRAPH)
    session.add(version)
    await session.flush()

    agent.current_version_id = version.id
    await session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="running",
        input_json={"input": "please run the calculation"},
    )
    session.add(run)
    await session.flush()
    await session.commit()
    return str(run.id)


def _make_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    factory: MagicMock = MagicMock(spec=async_sessionmaker)

    class _Ctx:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *_: object) -> None:
            pass

    factory.return_value = _Ctx()
    return factory  # type: ignore[return-value]


@pytest.fixture
async def checkpointer(db_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    dsn = _to_psycopg_dsn(db_url)
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        dsn,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    yield saver
    await pool.close()


def _build_compiled(checkpointer: AsyncPostgresSaver, db_session: AsyncSession) -> Any:
    # The tool node never reaches the LLM, but GraphCompiler requires one.
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    registry = ToolRegistry()
    register_builtins(registry)
    return (
        GraphCompiler(
            mock_llm,
            registry,
            _make_factory(db_session),
            tool_id_to_name={"calc": "calculator"},
            checkpointer=checkpointer,
        )
        .compile(APPROVAL_GRAPH)
        .graph
    )


async def test_require_approval_pauses_graph_with_interrupt(
    checkpointer: AsyncPostgresSaver, db_session: AsyncSession
) -> None:
    compiled = _build_compiled(checkpointer, db_session)
    thread_id = "approval-thread-1"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    run_id = await _seed_run_id(db_session)
    result = await compiled.ainvoke(_seed_state_with_pending_tool_call(run_id), config)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert payload["tool_name"] == "calculator"
    assert payload["args"] == {"expression": "1+1"}


async def test_approve_resumes_and_tool_executes(
    checkpointer: AsyncPostgresSaver, db_session: AsyncSession
) -> None:
    compiled = _build_compiled(checkpointer, db_session)
    thread_id = "approval-thread-2"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    run_id = await _seed_run_id(db_session)
    paused = await compiled.ainvoke(_seed_state_with_pending_tool_call(run_id), config)
    assert "__interrupt__" in paused

    resumed = await compiled.ainvoke(Command(resume="approved"), config)
    assert "__interrupt__" not in resumed
    tool_msgs = [m for m in resumed["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "2" in tool_msgs[0]["content"]


async def test_reject_raises_and_does_not_execute_tool(
    checkpointer: AsyncPostgresSaver, db_session: AsyncSession
) -> None:
    compiled = _build_compiled(checkpointer, db_session)
    thread_id = "approval-thread-3"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    run_id = await _seed_run_id(db_session)
    paused = await compiled.ainvoke(_seed_state_with_pending_tool_call(run_id), config)
    assert "__interrupt__" in paused

    with pytest.raises(AgentRuntimeError, match="rejected"):
        await compiled.ainvoke(Command(resume="rejected"), config)
