"""Integration tests for POST /agents/{id}/run and GET /runs/{id}.

Phase 3: /run now returns 202 + run_id (async enqueue). The arq pool is mocked
so no real Redis is required. Actual graph execution is tested via the worker task
tests (test_execute_run.py).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.dependencies import get_arq_pool
from app.main import app
from app.repositories.run import RunRepo

# ---------------------------------------------------------------------------
# Helpers to build graphs
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


async def register_and_login(client: AsyncClient, email: str, password: str = "password123") -> str:
    resp = await client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code in (200, 201), resp.text
    return str(resp.json()["access_token"])


# ---------------------------------------------------------------------------
# arq pool mock
# ---------------------------------------------------------------------------


def _mock_arq_pool() -> AsyncMock:
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=MagicMock())
    return pool


def _override_arq(pool: AsyncMock) -> None:
    async def _dep() -> AsyncMock:
        yield pool

    app.dependency_overrides[get_arq_pool] = _dep


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"run_user_{uuid.uuid4().hex[:8]}@example.com"
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    email = f"other_run_{uuid.uuid4().hex[:8]}@example.com"
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def agent_id(client: AsyncClient, auth_headers: dict[str, str]) -> str:
    create = await client.post("/agents", json={"name": "Test Runner"}, headers=auth_headers)
    aid = create.json()["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"graph_json": SIMPLE_GRAPH},
        headers=auth_headers,
    )
    return str(aid)


# ---------------------------------------------------------------------------
# Helpers to insert run rows directly (bypassing the async worker)
# ---------------------------------------------------------------------------


async def _insert_succeeded_run(
    db_session: Any, agent_id_str: str, agent_version_id_str: str
) -> str:
    """Insert a completed run row so GET /runs/{id} tests don't need the worker."""
    repo = RunRepo()
    run = await repo.create(
        db_session,
        agent_id=uuid.UUID(agent_id_str),
        agent_version_id=uuid.UUID(agent_version_id_str),
        thread_id=str(uuid.uuid4()),
        input_json={"input": "hi"},
    )
    await repo.update_status(
        db_session,
        run,
        "succeeded",
        output_json={"output": "hello"},
    )
    await db_session.commit()
    return str(run.id)


# ---------------------------------------------------------------------------
# Tests: 202 enqueue path
# ---------------------------------------------------------------------------


async def test_run_agent_returns_202_and_pending(
    client: AsyncClient, auth_headers: dict[str, str], agent_id: str
) -> None:
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/agents/{agent_id}/run",
            json={"input": "what is the answer?"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "pending"
    # run_id must be a valid UUID
    uuid.UUID(data["run_id"])


async def test_run_agent_enqueues_execute_run_job(
    client: AsyncClient, auth_headers: dict[str, str], agent_id: str
) -> None:
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/agents/{agent_id}/run",
            json={"input": "hello"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 202, resp.text
    run_id = resp.json()["run_id"]
    pool.enqueue_job.assert_called_once_with("execute_run", run_id)


# ---------------------------------------------------------------------------
# Tests: validation errors (must still fire before enqueue)
# ---------------------------------------------------------------------------


async def test_run_agent_no_version_returns_400(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "No Version"}, headers=auth_headers)
    aid = create.json()["id"]
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/agents/{aid}/run",
            json={"input": "hi"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 400
    pool.enqueue_job.assert_not_called()


async def test_run_nonexistent_agent_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            "/agents/00000000-0000-0000-0000-000000000099/run",
            json={"input": "hi"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 404
    pool.enqueue_job.assert_not_called()


async def test_run_other_users_agent_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/agents/{agent_id}/run",
            json={"input": "hi"},
            headers=other_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 403
    pool.enqueue_job.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: GET /runs/{id}
# ---------------------------------------------------------------------------


async def test_get_run_returns_correct_data(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    # Get the version ID for the agent so we can insert a run directly
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]

    run_id = await _insert_succeeded_run(db_session, agent_id, version_id)

    get_resp = await client.get(f"/runs/{run_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == run_id
    assert data["status"] == "succeeded"
    assert data["output_json"]["output"] == "hello"


async def test_get_run_other_user_returns_403(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    run_id = await _insert_succeeded_run(db_session, agent_id, version_id)

    resp = await client.get(f"/runs/{run_id}", headers=other_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /agents/{id}/runs
# ---------------------------------------------------------------------------


async def test_list_runs_by_agent_returns_all_runs(
    client: AsyncClient,
    db_session: Any,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]
    await _insert_succeeded_run(db_session, agent_id, version_id)
    await _insert_succeeded_run(db_session, agent_id, version_id)

    resp = await client.get(f"/agents/{agent_id}/runs", headers=auth_headers)
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2
    assert all(r["agent_id"] == agent_id for r in runs)


async def test_list_runs_by_agent_empty_list(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "Fresh"}, headers=auth_headers)
    aid = create.json()["id"]
    resp = await client.get(f"/agents/{aid}/runs", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_runs_other_user_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    resp = await client.get(f"/agents/{agent_id}/runs", headers=other_headers)
    assert resp.status_code == 403
