"""Integration tests for /templates and /agents/from-template endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template

SIMPLE_GRAPH = {
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


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "template_user@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def seeded_template(db_session: AsyncSession) -> Template:
    template = Template(
        name="Research Assistant",
        description="Summarizes a topic.",
        category="research",
        graph_json=SIMPLE_GRAPH,
    )
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)
    return template


async def test_list_templates(
    client: AsyncClient, auth_headers: dict[str, str], seeded_template: Template
) -> None:
    resp = await client.get("/templates", headers=auth_headers)
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Research Assistant" in names


async def test_create_agent_from_template(
    client: AsyncClient, auth_headers: dict[str, str], seeded_template: Template
) -> None:
    resp = await client.post(f"/agents/from-template/{seeded_template.id}", headers=auth_headers)
    assert resp.status_code == 201
    agent = resp.json()
    assert agent["name"] == "Research Assistant"
    assert agent["visibility"] == "private"
    assert agent["current_version_id"] is not None

    versions = await client.get(f"/agents/{agent['id']}", headers=auth_headers)
    assert versions.status_code == 200


async def test_create_agent_from_missing_template_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/agents/from-template/00000000-0000-0000-0000-000000000001",
        headers=auth_headers,
    )
    assert resp.status_code == 404
