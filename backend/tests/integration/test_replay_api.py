"""Integration tests for POST /runs/{id}/replay?from_step=N (fork)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_arq_pool, get_checkpointer
from app.llm.provider import LLMProvider, LLMResponse
from app.main import app
from app.repositories.run import RunRepo
from app.runtime.builtins import register_builtins
from app.runtime.checkpointer import _to_psycopg_dsn
from app.runtime.compiler import GraphCompiler
from app.runtime.executor import execute_graph
from app.runtime.registry import ToolRegistry
from tests.unit.runtime.conftest import dummy_session_factory

REPLAY_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "in", "type": "input"},
        {"id": "llm1", "type": "llm", "data": {"system_prompt": "Step 1.", "tools": []}},
        {"id": "llm2", "type": "llm", "data": {"system_prompt": "Step 2.", "tools": []}},
        {"id": "out", "type": "output"},
    ],
    "edges": [
        {"source": "in", "target": "llm1"},
        {"source": "llm1", "target": "llm2"},
        {"source": "llm2", "target": "out"},
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
    async def _dep() -> AsyncIterator[AsyncMock]:
        yield pool

    app.dependency_overrides[get_arq_pool] = _dep


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


@pytest.fixture
async def client(
    db_session: AsyncSession, checkpointer: AsyncPostgresSaver
) -> AsyncIterator[AsyncClient]:
    from app.db import get_session

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_checkpointer() -> AsyncPostgresSaver:
        return checkpointer

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_checkpointer] = _override_checkpointer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"replay_user_{uuid.uuid4().hex[:8]}@example.com"
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    email = f"replay_other_{uuid.uuid4().hex[:8]}@example.com"
    token = await register_and_login(client, email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def agent_id(client: AsyncClient, auth_headers: dict[str, str]) -> str:
    create = await client.post("/agents", json={"name": "Replay Test"}, headers=auth_headers)
    aid = create.json()["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"graph_json": REPLAY_GRAPH},
        headers=auth_headers,
    )
    return str(aid)


async def _run_graph_to_completion(checkpointer: AsyncPostgresSaver, thread_id: str) -> None:
    """Drive REPLAY_GRAPH to completion on thread_id so it has real checkpoint
    history to fork from — no worker/mocked-DB plumbing needed, just the
    compiled graph + a mocked LLM."""
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(content="step 1 done", tool_calls=[]),
        LLMResponse(content="step 2 done", tool_calls=[]),
    ]
    registry = ToolRegistry()
    register_builtins(registry)
    compiled = (
        GraphCompiler(mock_llm, registry, dummy_session_factory, checkpointer=checkpointer)
        .compile(REPLAY_GRAPH)
        .graph
    )

    await execute_graph(
        compiled,
        run_id="seed",
        thread_id=thread_id,
        user_input="go",
    )


async def _insert_run(
    db_session: AsyncSession, agent_id_str: str, agent_version_id_str: str, thread_id: str
) -> str:
    repo = RunRepo()
    run = await repo.create(
        db_session,
        agent_id=uuid.UUID(agent_id_str),
        agent_version_id=uuid.UUID(agent_version_id_str),
        thread_id=thread_id,
        input_json={"input": "go"},
    )
    await repo.update_status(db_session, run, "succeeded", output_json={"output": "step 2 done"})
    await db_session.commit()
    return str(run.id)


async def test_replay_creates_new_run_with_new_thread_id(
    client: AsyncClient,
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]

    old_thread_id = str(uuid.uuid4())
    await _run_graph_to_completion(checkpointer, old_thread_id)
    old_run_id = await _insert_run(db_session, agent_id, version_id, old_thread_id)

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/runs/{old_run_id}/replay",
            params={"from_step": 1},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    new_run_id = data["run_id"]
    assert new_run_id != old_run_id
    assert data["status"] == "pending"
    pool.enqueue_job.assert_called_once_with("execute_run", new_run_id, resume=True)

    repo = RunRepo()
    new_run = await repo.get(db_session, uuid.UUID(new_run_id))
    assert new_run is not None
    assert new_run.thread_id != old_thread_id
    assert new_run.agent_version_id == uuid.UUID(version_id)


async def test_replay_then_resume_execute_reaches_succeeded(
    client: AsyncClient,
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]

    old_thread_id = str(uuid.uuid4())
    await _run_graph_to_completion(checkpointer, old_thread_id)
    old_run_id = await _insert_run(db_session, agent_id, version_id, old_thread_id)

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/runs/{old_run_id}/replay",
            params={"from_step": 1},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 200, resp.text
    new_thread_id = (await RunRepo().get(db_session, uuid.UUID(resp.json()["run_id"]))).thread_id  # type: ignore[union-attr]

    # Forked checkpoint should already hold step 1's state (llm1 done, llm2 not yet run).
    mock_llm: LLMProvider = AsyncMock(spec=LLMProvider)
    mock_llm.chat.return_value = LLMResponse(content="step 2 redone", tool_calls=[])  # type: ignore[attr-defined]
    registry = ToolRegistry()
    register_builtins(registry)
    compiled = (
        GraphCompiler(mock_llm, registry, dummy_session_factory, checkpointer=checkpointer)
        .compile(REPLAY_GRAPH)
        .graph
    )

    result = await execute_graph(
        compiled,
        run_id="resumed",
        thread_id=new_thread_id,
        user_input=None,
        resume=True,
    )
    assert result.output == "step 2 redone"
    # llm1 was never re-invoked on the forked thread — only llm2 ran.
    assert mock_llm.chat.call_count == 1  # type: ignore[attr-defined]


async def test_replay_invalid_from_step_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]

    old_thread_id = str(uuid.uuid4())
    await _run_graph_to_completion(checkpointer, old_thread_id)
    old_run_id = await _insert_run(db_session, agent_id, version_id, old_thread_id)

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/runs/{old_run_id}/replay",
            params={"from_step": 99},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 400
    pool.enqueue_job.assert_not_called()


async def test_replay_negative_from_step_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
    auth_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]

    old_thread_id = str(uuid.uuid4())
    await _run_graph_to_completion(checkpointer, old_thread_id)
    old_run_id = await _insert_run(db_session, agent_id, version_id, old_thread_id)

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/runs/{old_run_id}/replay",
            params={"from_step": -1},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 422
    pool.enqueue_job.assert_not_called()


async def test_replay_other_users_run_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    checkpointer: AsyncPostgresSaver,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    agent_resp = await client.get(f"/agents/{agent_id}", headers=auth_headers)
    version_id = agent_resp.json()["current_version_id"]

    old_thread_id = str(uuid.uuid4())
    await _run_graph_to_completion(checkpointer, old_thread_id)
    old_run_id = await _insert_run(db_session, agent_id, version_id, old_thread_id)

    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            f"/runs/{old_run_id}/replay",
            params={"from_step": 1},
            headers=other_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 403


async def test_replay_nonexistent_run_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    pool = _mock_arq_pool()
    _override_arq(pool)
    try:
        resp = await client.post(
            "/runs/00000000-0000-0000-0000-000000000099/replay",
            params={"from_step": 0},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)

    assert resp.status_code == 404
