"""Integration tests for GET /runs/{id}/events SSE endpoint.

These tests use a completed run (status=succeeded) so the SSE endpoint
only replays from DB and returns immediately — no live Redis subscription needed.
The Redis dependency is mocked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_redis
from app.main import app
from app.models.agent import Agent, AgentVersion
from app.models.run import Run
from app.models.user import User
from app.repositories.run import RunRepo

FIXED_DT = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def _mock_redis() -> AsyncMock:
    """Return a mock Redis client that has an aclose and pubsub that never delivers messages."""
    redis = AsyncMock()
    pubsub = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    redis.pubsub.return_value = pubsub
    return redis


def _override_redis(mock: AsyncMock) -> None:
    async def _dep() -> AsyncMock:
        yield mock

    app.dependency_overrides[get_redis] = _dep


async def _seed_succeeded_run_with_events(
    session: AsyncSession, n_events: int = 2
) -> tuple[Run, str]:
    """Seed a user, agent, version, succeeded run, and n_events run_events. Returns (run, token)."""
    from app.config import get_settings
    from app.security import create_access_token

    user = User(email=f"sse_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    await session.flush()

    agent = Agent(owner_id=user.id, name="sse-agent")
    session.add(agent)
    await session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json={})
    session.add(version)
    await session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="succeeded",
        input_json={"input": "hi"},
        output_json={"output": "done"},
    )
    session.add(run)
    await session.flush()

    repo = RunRepo()
    for i in range(n_events):
        await repo.create_event(
            session,
            run_id=run.id,
            step_index=i,
            node_id=f"node{i}",
            event_type="node_start",
            payload_json={"step": i},
            ts=FIXED_DT,
        )

    await session.commit()

    settings = get_settings()
    token = create_access_token(str(user.id), settings)
    return run, token


def _parse_sse_frames(body: str) -> list[dict[str, Any]]:
    import json

    frames = []
    current: dict[str, Any] = {}
    for line in body.splitlines():
        if line.startswith("id:"):
            current["id"] = line[3:].strip()
        elif line.startswith("data:"):
            raw = line[5:].strip()
            try:
                current["data"] = json.loads(raw)
            except Exception:
                current["data"] = raw
        elif line == "" and current:
            frames.append(current)
            current = {}
    if current:
        frames.append(current)
    return frames


async def test_sse_replays_db_events_for_succeeded_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    run, token = await _seed_succeeded_run_with_events(db_session, n_events=2)
    mock_redis = _mock_redis()
    _override_redis(mock_redis)
    try:
        async with client.stream(
            "GET",
            f"/runs/{run.id}/events",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()
    finally:
        app.dependency_overrides.pop(get_redis, None)

    frames = _parse_sse_frames(body.decode())
    event_frames = [f for f in frames if f.get("data", {}).get("type") != "done"]
    assert len(event_frames) == 2
    step_ids = [int(f["id"]) for f in event_frames]
    assert step_ids == [0, 1]


async def test_sse_respects_last_event_id(client: AsyncClient, db_session: AsyncSession) -> None:
    run, token = await _seed_succeeded_run_with_events(db_session, n_events=3)
    mock_redis = _mock_redis()
    _override_redis(mock_redis)
    try:
        async with client.stream(
            "GET",
            f"/runs/{run.id}/events",
            headers={
                "Authorization": f"Bearer {token}",
                "Last-Event-ID": "0",
            },
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()
    finally:
        app.dependency_overrides.pop(get_redis, None)

    frames = _parse_sse_frames(body.decode())
    event_frames = [f for f in frames if f.get("data", {}).get("type") != "done"]
    step_ids = [int(f["id"]) for f in event_frames]
    assert step_ids == [1, 2]


async def test_sse_done_frame_for_terminal_run(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    run, token = await _seed_succeeded_run_with_events(db_session, n_events=0)
    mock_redis = _mock_redis()
    _override_redis(mock_redis)
    try:
        async with client.stream(
            "GET",
            f"/runs/{run.id}/events",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            body = await resp.aread()
    finally:
        app.dependency_overrides.pop(get_redis, None)

    frames = _parse_sse_frames(body.decode())
    done_frames = [f for f in frames if f.get("data", {}).get("type") == "done"]
    assert len(done_frames) == 1
    assert done_frames[0]["data"]["status"] == "succeeded"


async def test_sse_emits_done_even_if_live_poll_raises(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A still-running run whose live poll loop hits an unexpected exception
    (DB hiccup, Redis hiccup, anything) must still terminate the SSE stream
    with a terminal frame, not die silently — otherwise a client that only
    reacts to the 'done' event hangs on "running" forever even though the
    backing HTTP connection already closed.
    """
    from app.config import get_settings
    from app.security import create_access_token

    user = User(email=f"sse_exc_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    agent = Agent(owner_id=user.id, name="sse-agent")
    db_session.add(agent)
    await db_session.flush()

    version = AgentVersion(agent_id=agent.id, version_number=1, graph_json={})
    db_session.add(version)
    await db_session.flush()

    run = Run(
        agent_id=agent.id,
        agent_version_id=version.id,
        thread_id=str(uuid.uuid4()),
        status="running",
        input_json={"input": "hi"},
    )
    db_session.add(run)
    await db_session.flush()
    await db_session.commit()

    settings = get_settings()
    token = create_access_token(str(user.id), settings)

    # redis.asyncio.Redis.pubsub() is a plain sync method returning a PubSub
    # object (whose own methods are async) — MagicMock for the client so
    # .pubsub() itself isn't auto-wrapped as a coroutine like AsyncMock would.
    pubsub = AsyncMock()
    pubsub.get_message = AsyncMock(side_effect=ConnectionError("redis connection dropped"))
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = pubsub
    _override_redis(mock_redis)
    try:
        async with client.stream(
            "GET",
            f"/runs/{run.id}/events",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()
    finally:
        app.dependency_overrides.pop(get_redis, None)

    frames = _parse_sse_frames(body.decode())
    done_frames = [f for f in frames if f.get("data", {}).get("type") == "done"]
    assert len(done_frames) == 1
    assert done_frames[0]["data"]["status"] == "unknown"


async def test_sse_unauthorized_returns_401_or_403(client: AsyncClient) -> None:
    fake_run_id = uuid.uuid4()
    mock_redis = _mock_redis()
    _override_redis(mock_redis)
    try:
        resp = await client.get(f"/runs/{fake_run_id}/events")
    finally:
        app.dependency_overrides.pop(get_redis, None)
    assert resp.status_code in (401, 403)


async def test_sse_nonexistent_run_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.config import get_settings
    from app.security import create_access_token

    user = User(email=f"sse_404_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    settings = get_settings()
    token = create_access_token(str(user.id), settings)

    mock_redis = _mock_redis()
    _override_redis(mock_redis)
    try:
        fake_id = uuid.uuid4()
        resp = await client.get(
            f"/runs/{fake_id}/events",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_redis, None)
    assert resp.status_code == 404


async def test_sse_other_user_run_returns_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.config import get_settings
    from app.security import create_access_token

    run, _owner_token = await _seed_succeeded_run_with_events(db_session, n_events=0)

    other = User(email=f"sse_other_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
    db_session.add(other)
    await db_session.flush()
    await db_session.commit()

    settings = get_settings()
    other_token = create_access_token(str(other.id), settings)

    mock_redis = _mock_redis()
    _override_redis(mock_redis)
    try:
        resp = await client.get(
            f"/runs/{run.id}/events",
            headers={"Authorization": f"Bearer {other_token}"},
        )
    finally:
        app.dependency_overrides.pop(get_redis, None)
    assert resp.status_code == 403
