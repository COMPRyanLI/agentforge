"""The headline demo: kill the worker mid-run, restart, resume — the agent
finishes without re-calling the LLM for an already-checkpointed node, and
without re-firing a tool side effect that already completed.

Uses a real Postgres-backed AsyncPostgresSaver (not a mock) so the test
exercises the actual checkpoint/resume mechanism, not an assumption about it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import LLMResponse
from app.llm.provider import ToolCall as LLMToolCall
from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.run import ToolCall as ToolCallRow
from app.models.user import User
from app.repositories.run import RunRepo
from app.runtime.checkpointer import _to_psycopg_dsn
from app.workers.worker import execute_run

RECOVERY_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {
            "id": "llm1",
            "type": "llm",
            "data": {"system_prompt": "Step 1.", "tools": ["calculator"]},
        },
        {
            "id": "llm2",
            "type": "llm",
            "data": {
                "system_prompt": "Step 2.",
                "tools": [],
                "retry": {"max_retries": 0, "backoff_seconds": 0},
            },
        },
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "llm2"},
        {"source": "llm2", "target": "out"},
    ],
}


LOOP_RECOVERY_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {
            "id": "loop",
            "type": "loop",
            "data": {"expr": "step_index >= 0", "max_iterations": 3},
        },
        {
            "id": "llm1",
            "type": "llm",
            "data": {
                "system_prompt": "Iterate.",
                "tools": [],
                "retry": {"max_retries": 0, "backoff_seconds": 0},
            },
        },
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "loop"},
        {"source": "loop", "target": "llm1", "condition": "true"},
        {"source": "loop", "target": "out", "condition": "false"},
        {"source": "llm1", "target": "loop"},
    ],
}


async def _seed_pending_run(session: AsyncSession, graph_json: dict[str, Any]) -> Run:
    user = User(email=f"recovery_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()

    agent = Agent(owner_id=user.id, name="recovery-test-agent")
    session.add(agent)
    await session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json=graph_json)
    session.add(version)
    await session.flush()

    agent.current_version_id = version.id
    await session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="pending",
        input_json={"input": "what is 1+1, then say done?"},
    )
    session.add(run)
    await session.flush()
    await session.commit()
    return run


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


async def test_resume_after_crash_does_not_redo_completed_node_or_tool_call(
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
) -> None:
    run = await _seed_pending_run(db_session, RECOVERY_GRAPH)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    # llm1's internal tool-calling loop: call A returns a tool call, call B
    # (after the tool result is appended) returns the final text — llm1
    # completes cleanly and gets checkpointed.
    # llm2: call C raises (no retries configured) — run goes "interrupted"
    # with no checkpoint past llm1. On resume, llm2 alone re-enters from
    # scratch: call D succeeds.
    mock_llm.chat.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[LLMToolCall(name="calculator", arguments={"expression": "1+1"})],
        ),
        LLMResponse(content="step 1 done", tool_calls=[]),
        ConnectionError("ollama unreachable"),
        LLMResponse(content="step 2 done", tool_calls=[]),
    ]
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({"checkpointer": checkpointer}, run_id_str)

        repo = RunRepo()
        after_crash = await repo.get(db_session, uuid.UUID(run_id_str))
        assert after_crash is not None
        assert after_crash.status == "interrupted"
        assert mock_llm.chat.call_count == 3

        # Simulate a fresh worker process picking the job back up.
        await execute_run({"checkpointer": checkpointer}, run_id_str, resume=True)

    final = await repo.get(db_session, uuid.UUID(run_id_str))
    assert final is not None
    assert final.status == "succeeded"
    assert final.output_json is not None
    assert final.output_json.get("output") == "step 2 done"

    # +1, not +2: llm1's two internal calls are never redone on resume.
    assert mock_llm.chat.call_count == 4

    result = await db_session.execute(select(ToolCallRow).where(ToolCallRow.run_id == run.id))
    tool_calls = list(result.scalars().all())
    assert len(tool_calls) == 1
    assert tool_calls[0].status == "completed"


async def test_resume_mid_loop_continues_at_correct_iteration(
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
) -> None:
    """Crash on the loop body's 2nd iteration, resume, and confirm:
    - the 1st iteration's LLM call is never redone (proves the checkpointed
      loop_counters value, not a re-derived one, drives resume), and
    - the loop still runs exactly max_iterations (3) times total, ending
      cleanly via the forced-exit edge rather than running forever.
    """
    run = await _seed_pending_run(db_session, LOOP_RECOVERY_GRAPH)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = [
        LLMResponse(content="iter1 done", tool_calls=[]),
        ConnectionError("ollama unreachable"),  # iteration 2, 1st attempt: crash
        LLMResponse(content="iter2 done", tool_calls=[]),  # iteration 2, retried on resume
        LLMResponse(content="iter3 done", tool_calls=[]),
    ]
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({"checkpointer": checkpointer}, run_id_str)

        repo = RunRepo()
        after_crash = await repo.get(db_session, uuid.UUID(run_id_str))
        assert after_crash is not None
        assert after_crash.status == "interrupted"
        assert mock_llm.chat.call_count == 2

        await execute_run({"checkpointer": checkpointer}, run_id_str, resume=True)

    final = await repo.get(db_session, uuid.UUID(run_id_str))
    assert final is not None
    assert final.status == "succeeded"
    assert final.output_json is not None
    assert final.output_json.get("output") == "iter3 done"

    # 2 calls before the crash + 2 more after resume (the retried 2nd
    # iteration and the 3rd) = 4, never 5 — iteration 1 is not redone.
    assert mock_llm.chat.call_count == 4
