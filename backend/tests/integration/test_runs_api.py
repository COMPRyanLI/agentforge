"""Integration tests for POST /agents/{id}/run and GET /runs/{id}.

All tests use a stubbed LLMProvider — no live Ollama required in CI.
The mock LLM has scripted responses so tests are fully deterministic.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import get_session
from app.dependencies import get_llm_provider
from app.llm.provider import LLMProvider, LLMResponse, ToolCall
from app.main import app
from app.models.run import Run

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


def calc_graph(tool_names: list[str]) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "in", "type": "input"},
            {
                "id": "llm1",
                "type": "llm",
                "data": {"system_prompt": "Use tools.", "tools": tool_names},
            },
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
# LLM mock helpers
# ---------------------------------------------------------------------------


def plain_text_llm(reply: str) -> LLMProvider:
    m: LLMProvider = AsyncMock(spec=LLMProvider)
    m.chat.return_value = LLMResponse(content=reply, tool_calls=[])  # type: ignore[attr-defined]
    return m


def tool_calling_llm(tool_name: str, expression: str, final_reply: str) -> LLMProvider:
    """First call returns a tool_call, second returns the answer."""
    m: LLMProvider = AsyncMock(spec=LLMProvider)
    m.chat.side_effect = [  # type: ignore[attr-defined]
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(name=tool_name, arguments={"expression": expression})],
        ),
        LLMResponse(content=final_reply, tool_calls=[]),
    ]
    return m


def error_llm() -> LLMProvider:
    m: LLMProvider = AsyncMock(spec=LLMProvider)
    m.chat.side_effect = RuntimeError("Ollama connection refused")  # type: ignore[attr-defined]
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    # Unique email per invocation: the run service commits before execute_graph,
    # so registered users persist in the DB beyond the test's rollback.
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
    """Create an agent with a simple graph version, return its id."""
    create = await client.post("/agents", json={"name": "Test Runner"}, headers=auth_headers)
    aid = create.json()["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"graph_json": SIMPLE_GRAPH},
        headers=auth_headers,
    )
    return str(aid)


@pytest.fixture
async def calc_agent_id(client: AsyncClient, auth_headers: dict[str, str]) -> str:
    """Create an agent whose LLM node references the 'calculator' builtin."""
    create = await client.post("/agents", json={"name": "Calc Agent"}, headers=auth_headers)
    aid = create.json()["id"]
    await client.post(
        f"/agents/{aid}/versions",
        json={"graph_json": calc_graph(["calculator"])},
        headers=auth_headers,
    )
    return str(aid)


# ---------------------------------------------------------------------------
# Tests: basic run lifecycle
# ---------------------------------------------------------------------------


async def test_run_agent_succeeds(
    client: AsyncClient, auth_headers: dict[str, str], agent_id: str
) -> None:
    mock = plain_text_llm("42 is the answer.")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        resp = await client.post(
            f"/agents/{agent_id}/run",
            json={"input": "what is the answer to life?"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "succeeded"
    assert data["output_json"]["output"] == "42 is the answer."
    assert data["error_json"] is None


async def test_get_run_returns_correct_data(
    client: AsyncClient, auth_headers: dict[str, str], agent_id: str
) -> None:
    mock = plain_text_llm("hello")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        run_resp = await client.post(
            f"/agents/{agent_id}/run",
            json={"input": "hi"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    run_id = run_resp.json()["id"]
    get_resp = await client.get(f"/runs/{run_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == run_id
    assert get_resp.json()["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Tests: error conditions
# ---------------------------------------------------------------------------


async def test_run_agent_no_version_returns_400(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "No Version"}, headers=auth_headers)
    aid = create.json()["id"]

    mock = plain_text_llm("should not be called")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        resp = await client.post(
            f"/agents/{aid}/run",
            json={"input": "hi"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 400


async def test_run_nonexistent_agent_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    mock = plain_text_llm("no")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        resp = await client.post(
            "/agents/00000000-0000-0000-0000-000000000099/run",
            json={"input": "hi"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 404


async def test_run_other_users_agent_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    mock = plain_text_llm("should not run")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        resp = await client.post(
            f"/agents/{agent_id}/run",
            json={"input": "hi"},
            headers=other_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 403


async def test_llm_error_persists_failed_run(
    db_session: Any, auth_headers: dict[str, str], agent_id: str
) -> None:
    """Unexpected LLM errors should return 500 (re-raise path in RunService).

    The httpx ASGI transport re-raises server exceptions by default, hiding the
    5xx response. We use raise_app_exceptions=False so we can assert the status.
    """
    mock = error_llm()
    app.dependency_overrides[get_llm_provider] = lambda: mock

    async def _session() -> Any:
        yield db_session

    app.dependency_overrides[get_session] = _session
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as no_raise_client:
            resp = await no_raise_client.post(
                f"/agents/{agent_id}/run",
                json={"input": "break things"},
                headers=auth_headers,
            )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 500

    # The run record must have been committed as "failed" before the re-raise,
    # so it survives the session rollback that get_session performs on exception.
    result = await db_session.execute(select(Run).where(Run.agent_id == uuid.UUID(agent_id)))
    failed_run = result.scalar_one_or_none()
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.error_json is not None


async def test_get_run_other_user_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
    agent_id: str,
) -> None:
    mock = plain_text_llm("hi")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        run_resp = await client.post(
            f"/agents/{agent_id}/run", json={"input": "hi"}, headers=auth_headers
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    run_id = run_resp.json()["id"]
    resp = await client.get(f"/runs/{run_id}", headers=other_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Core demo: deterministic tool-calling scenario
# ---------------------------------------------------------------------------


async def test_tool_calling_calculator_end_to_end(
    client: AsyncClient,
    auth_headers: dict[str, str],
    calc_agent_id: str,
) -> None:
    """The headline Phase 2 demo: POST a question → LLM calls calculator → answer returned.

    Uses a scripted mock LLM so no Ollama is needed in CI.
    The mock:
      - Call 1: returns tool_call for calculator with expression "6*7"
      - Call 2: returns "6 times 7 is 42."
    Asserts: status==succeeded, output contains "42", LLM called exactly twice.
    """
    mock = tool_calling_llm("calculator", "6*7", "6 times 7 is 42.")
    app.dependency_overrides[get_llm_provider] = lambda: mock
    try:
        resp = await client.post(
            f"/agents/{calc_agent_id}/run",
            json={"input": "what is 6 times 7?"},
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "succeeded"
    assert "42" in data["output_json"]["output"]
    assert mock.chat.call_count == 2  # type: ignore[attr-defined]
