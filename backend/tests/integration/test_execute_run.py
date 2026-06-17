"""Integration tests for the execute_run arq worker task.

Uses a real DB (db_session fixture) but mocks the LLM and Redis so
no live Ollama or Redis is needed in CI.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.provider import LLMResponse
from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.user import User
from app.repositories.run import RunRepo
from app.workers.worker import execute_run

SIMPLE_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "llm1", "type": "llm", "data": {"system_prompt": "Be helpful.", "tools": []}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "out"},
    ],
}


async def _seed_pending_run(session: AsyncSession) -> Run:
    user = User(email=f"worker_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()

    agent = Agent(owner_id=user.id, name="worker-test-agent")
    session.add(agent)
    await session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json=SIMPLE_GRAPH)
    session.add(version)
    await session.flush()

    agent.current_version_id = version.id
    await session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="pending",
        input_json={"input": "what is the answer?"},
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


async def test_execute_run_sets_succeeded_status(db_session: AsyncSession) -> None:
    run = await _seed_pending_run(db_session)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(content="42 is the answer.", tool_calls=[])
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.output_json is not None
    assert "42 is the answer." in updated.output_json.get("output", "")


async def test_execute_run_sets_failed_on_llm_error(db_session: AsyncSession) -> None:
    run = await _seed_pending_run(db_session)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.side_effect = RuntimeError("LLM connection refused")
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    repo = RunRepo()
    updated = await repo.get(db_session, uuid.UUID(run_id_str))
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error_json is not None


async def test_execute_run_not_found_returns_gracefully() -> None:
    """A missing run_id should log and return without raising."""
    fake_id = str(uuid.uuid4())
    mock_redis = AsyncMock()

    class _EmptyCtx:
        async def __aenter__(self) -> AsyncSession:
            s = AsyncMock(spec=AsyncSession)
            s.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            return s

        async def __aexit__(self, *_: object) -> None:
            pass

    factory: MagicMock = MagicMock(spec=async_sessionmaker)
    factory.return_value = _EmptyCtx()

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
    ):
        await execute_run({}, fake_id)


async def test_execute_run_publishes_events(db_session: AsyncSession) -> None:
    run = await _seed_pending_run(db_session)
    run_id_str = str(run.id)

    mock_redis = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(content="done", tool_calls=[])
    factory = _make_factory(db_session)

    with (
        patch("app.workers.worker.redis_asyncio.from_url", return_value=mock_redis),
        patch("app.workers.worker.async_sessionmaker", return_value=factory),
        patch("app.workers.worker.OllamaProvider", return_value=mock_llm),
    ):
        await execute_run({}, run_id_str)

    # At least some Redis publishes should have happened (one per node event)
    assert mock_redis.publish.call_count > 0
    # All publishes should be to the correct channel
    for call in mock_redis.publish.call_args_list:
        channel = call.args[0]
        assert channel == f"run:{run_id_str}"
