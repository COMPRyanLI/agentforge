"""Integration tests for EventEmitter (requires real DB via db_session fixture)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.user import User
from app.repositories.run import RunRepo
from app.runtime.event_emitter import EventEmitter

FIXED_DT = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)


def _make_session_factory(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """Return a factory that yields the given session (for test isolation)."""
    factory: MagicMock = MagicMock(spec=async_sessionmaker)

    class _FakeCtx:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *_: object) -> None:
            pass

    factory.return_value = _FakeCtx()
    return factory  # type: ignore[return-value]


async def _seed_run(session: AsyncSession) -> Run:
    user = User(email=f"ee_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()
    agent = Agent(owner_id=user.id, name="ee-agent")
    session.add(agent)
    await session.flush()
    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json={})
    session.add(version)
    await session.flush()
    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="running",
        input_json={"input": "test"},
    )
    session.add(run)
    await session.flush()
    return run


async def test_emit_writes_run_event_and_publishes(db_session: AsyncSession) -> None:
    run = await _seed_run(db_session)
    redis_mock = AsyncMock()
    factory = _make_session_factory(db_session)

    emitter = EventEmitter(str(run.id), factory, redis_mock)
    await emitter.emit(
        step_index=0,
        node_id="llm1",
        event_type="node_start",
        payload={"info": "starting"},
        ts=FIXED_DT,
    )
    await db_session.commit()

    redis_mock.publish.assert_called_once()
    channel_arg, message_arg = redis_mock.publish.call_args.args
    assert channel_arg == f"run:{run.id}"
    published = json.loads(message_arg)
    assert published["step_index"] == 0
    assert published["node_id"] == "llm1"
    assert published["event_type"] == "node_start"
    assert published["ts"] == FIXED_DT.isoformat()

    repo = RunRepo()
    events = await repo.list_events(db_session, run.id)
    assert len(events) == 1
    assert events[0].step_index == 0
    assert events[0].node_id == "llm1"
    assert events[0].event_type == "node_start"
    assert events[0].payload_json == {"info": "starting"}
    assert events[0].ts == FIXED_DT


async def test_emit_multiple_events_in_order(db_session: AsyncSession) -> None:
    run = await _seed_run(db_session)
    redis_mock = AsyncMock()
    factory = _make_session_factory(db_session)
    emitter = EventEmitter(str(run.id), factory, redis_mock)

    for i, etype in enumerate(["node_start", "llm_call", "node_end"]):
        await emitter.emit(step_index=i, node_id="llm1", event_type=etype, payload={}, ts=FIXED_DT)
    await db_session.commit()

    assert redis_mock.publish.call_count == 3
    repo = RunRepo()
    events = await repo.list_events(db_session, run.id)
    assert [e.event_type for e in events] == ["node_start", "llm_call", "node_end"]
