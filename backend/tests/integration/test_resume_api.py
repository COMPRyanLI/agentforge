"""Integration tests for POST /runs/{id}/resume."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.dependencies import get_arq_pool
from app.main import app
from app.repositories.run import RunRepo

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


async def register_and_login(client: AsyncClient, email: str, password: str = "password123") -> str:
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["access_token"])


def _mock_arq_pool() -> AsyncMock:
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=MagicMock())
    return pool


def _override_arq(pool: AsyncMock) -> None:
    async def _dep() -> AsyncMock:
        yield pool

    app.dependency_overrides[get_arq_pool] = _dep


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"resume_user_{uuid.uuid4().hex[:8]}@example.com"
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    email = f"resume_other_{uuid.uuid4().hex[:8]}@example.com"
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def agent_id(client: AsyncClient, auth_headers: dict[str, str]) -> str:
    create = await client.post("/agents", json={"name": "Resume Test"}, headers=auth_headers)
    aid = create.json()["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"graph_json": SIMPLE_GRAPH},
        headers=auth_headers,
    )
    return str(aid)


async def _insert_run(
    db_session: Any, agent_id_str: str, agent_version_id_str: str, status: str
) -> str:
    repo = RunRepo()
    run = await repo.create(
        db_session,
        agent_id=uuid.UUID(agent_id_str),
        agent_version_id=uuid.UUID(agent_version_id_str),
        thread_id=str(uuid.uuid4()),
        input_json={"input": "hi"},
    )
    await repo.update_status(db_session, run, status)
    await db_session.commit()
    return str(run.id)


async def test_resume_interrupted_run_returns_200_pending(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    run_id = await _insert_run(db_session, agent_id, version_id, "interrupted")

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(f"/runs/{run_id}/resume", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["run_id"] == run_id
    assert data["status"] == "pending"
    pool.enqueue_job.assert_called_once_with("execute_run", run_id, resume=True, resume_value=None)


async def test_resume_running_run_is_allowed(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    """A killed worker leaves the run stuck at 'running' — resume must accept that."""
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    run_id = await _insert_run(db_session, agent_id, version_id, "running")

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(f"/runs/{run_id}/resume", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"


async def test_resume_succeeded_run_returns_400(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    run_id = await _insert_run(db_session, agent_id, version_id, "succeeded")

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(f"/runs/{run_id}/resume", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 400
    pool.enqueue_job.assert_not_called()


async def test_resume_failed_run_returns_400(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    run_id = await _insert_run(db_session, agent_id, version_id, "failed")

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(f"/runs/{run_id}/resume", headers=auth_headers)
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 400


async def test_resume_other_users_run_returns_403(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    run_id = await _insert_run(db_session, agent_id, version_id, "interrupted")

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(f"/runs/{run_id}/resume", headers=other_headers)
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 403


async def test_resume_nonexistent_run_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            "/runs/00000000-0000-0000-0000-000000000099/resume", headers=auth_headers
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 404
