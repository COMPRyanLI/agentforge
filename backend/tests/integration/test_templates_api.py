"""Integration tests for /templates and /agents/from-template endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template
from app.repositories.template import TemplateRepo
from app.scripts.seed_templates import TEMPLATES, _apply_templates

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

    # The clone's actual persisted graph must be the template's full graph,
    # not a default skeleton — this is the regression guard for the "opening
    # a template shows the default in->llm->out skeleton" bug (Case A would
    # be the backend storing a default/empty graph instead of this).
    current_version = await client.get(
        f"/agents/{agent['id']}/versions/current", headers=auth_headers
    )
    assert current_version.status_code == 200
    body = current_version.json()
    assert body["version_number"] == 1
    assert body["graph_json"] == seeded_template.graph_json


async def test_create_agent_from_missing_template_returns_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/agents/from-template/00000000-0000-0000-0000-000000000001",
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_apply_templates_upserts_and_prunes(db_session: AsyncSession) -> None:
    """Re-running the seed against rows with old data/old names must converge
    the table to exactly TEMPLATES: matching names get their fields updated in
    place, and any name no longer defined (a rename or removal) is deleted."""
    repo = TemplateRepo()

    stale = Template(
        name="Some Old Template",
        description="no longer defined",
        category="legacy",
        graph_json=SIMPLE_GRAPH,
    )
    outdated = Template(
        name=TEMPLATES[0]["name"],
        description="stale description",
        category="stale-category",
        graph_json=SIMPLE_GRAPH,
    )
    db_session.add_all([stale, outdated])
    await db_session.flush()

    await _apply_templates(db_session)
    await db_session.flush()

    rows = await repo.list_all(db_session)
    names = {row.name for row in rows}
    assert names == {spec["name"] for spec in TEMPLATES}

    updated = await repo.get_by_name(db_session, TEMPLATES[0]["name"])
    assert updated is not None
    assert updated.description == TEMPLATES[0]["description"]
    assert updated.graph_json == TEMPLATES[0]["graph_json"]

    # Re-applying again (idempotent) must not change the row count.
    await _apply_templates(db_session)
    await db_session.flush()
    rows_again = await repo.list_all(db_session)
    assert len(rows_again) == len(TEMPLATES)
