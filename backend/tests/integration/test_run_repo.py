"""Integration tests for RunRepo extensions: create_event, list_events, list_by_agent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.user import User
from app.repositories.run import RunRepo

FIXED_DT = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _make_run(session: AsyncSession) -> Run:
    """Create a minimal User→Agent→AgentVersion→Run chain for FK constraints."""
    user = User(email=f"repo_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()

    agent = Agent(owner_id=user.id, name="repo-test-agent")
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
        input_json={"input": "hi"},
    )
    session.add(run)
    await session.flush()
    return run


async def test_create_and_list_events_all(db_session: AsyncSession) -> None:
    repo = RunRepo()
    run = await _make_run(db_session)

    for i in range(3):
        await repo.create_event(
            db_session,
            run_id=run.id,
            step_index=i,
            node_id=f"node{i}",
            event_type="node_start",
            payload_json={"step": i},
            ts=FIXED_DT,
        )
    await db_session.commit()

    events = await repo.list_events(db_session, run.id)
    assert len(events) == 3
    assert [e.step_index for e in events] == [0, 1, 2]
    assert events[0].node_id == "node0"
    assert events[0].ts == FIXED_DT


async def test_list_events_after_step_filter(db_session: AsyncSession) -> None:
    repo = RunRepo()
    run = await _make_run(db_session)

    for i in range(3):
        await repo.create_event(
            db_session,
            run_id=run.id,
            step_index=i,
            node_id="llm",
            event_type="node_end",
            payload_json={},
            ts=FIXED_DT,
        )
    await db_session.commit()

    events = await repo.list_events(db_session, run.id, after_step=0)
    assert len(events) == 2
    assert [e.step_index for e in events] == [1, 2]


async def test_list_events_empty_when_no_events(db_session: AsyncSession) -> None:
    repo = RunRepo()
    run = await _make_run(db_session)

    events = await repo.list_events(db_session, run.id)
    assert events == []


async def test_list_by_agent_returns_all_runs(db_session: AsyncSession) -> None:
    repo = RunRepo()
    run1 = await _make_run(db_session)
    run2 = Run(
        agent_id=run1.agent_id,
        agent_version_id=run1.agent_version_id,
        thread_id=str(uuid.uuid4()),
        status="pending",
        input_json={"input": "second"},
    )
    db_session.add(run2)
    await db_session.flush()
    await db_session.commit()

    runs = await repo.list_by_agent(db_session, run1.agent_id)
    assert len(runs) == 2
    assert all(r.agent_id == run1.agent_id for r in runs)


async def test_list_by_agent_empty_when_no_runs(db_session: AsyncSession) -> None:
    repo = RunRepo()
    fake_agent_id = uuid.uuid4()
    runs = await repo.list_by_agent(db_session, fake_agent_id)
    assert runs == []
