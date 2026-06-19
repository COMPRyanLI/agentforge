"""Integration tests for /agents endpoints."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "agent_user@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "other_user@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_agent_authenticated(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        "/agents",
        json={"name": "My Agent", "description": "A test agent"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Agent"
    assert data["visibility"] == "private"


async def test_get_agent_unauthenticated_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/agents/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 401


async def test_list_agents_own_only(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    await client.post("/agents", json={"name": "Alice Agent"}, headers=auth_headers)
    await client.post("/agents", json={"name": "Bob Agent"}, headers=other_headers)

    resp = await client.get("/agents", headers=auth_headers)
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "Alice Agent" in names
    assert "Bob Agent" not in names


async def test_get_agent_other_owner_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    create = await client.post("/agents", json={"name": "Alice Agent"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.get(f"/agents/{agent_id}", headers=other_headers)
    assert resp.status_code == 403


async def test_patch_agent_other_owner_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    create = await client.post("/agents", json={"name": "My Agent"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.patch(
        f"/agents/{agent_id}",
        json={"name": "Hacked Name"},
        headers=other_headers,
    )
    assert resp.status_code == 403


async def test_create_version_and_publish(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "Versioned Agent"}, headers=auth_headers)
    agent_id = create.json()["id"]

    graph = {"nodes": [{"id": "in", "type": "input"}], "edges": []}
    ver_resp = await client.post(
        f"/agents/{agent_id}/versions",
        json={"graph_json": graph},
        headers=auth_headers,
    )
    assert ver_resp.status_code == 201
    assert ver_resp.json()["version_number"] == 1

    pub_resp = await client.post(f"/agents/{agent_id}/publish", headers=auth_headers)
    assert pub_resp.status_code == 200
    assert pub_resp.json()["visibility"] == "published"


async def test_publish_without_version_returns_400(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "Empty Agent"}, headers=auth_headers)
    agent_id = create.json()["id"]
    resp = await client.post(f"/agents/{agent_id}/publish", headers=auth_headers)
    assert resp.status_code == 400


async def test_publish_with_db_backed_tool_node_returns_400(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "Tool Agent"}, headers=auth_headers)
    agent_id = create.json()["id"]

    graph = {
        "nodes": [
            {"id": "in", "type": "input"},
            {
                "id": "t1",
                "type": "tool",
                "data": {"tool_id": "11111111-1111-1111-1111-111111111111"},
            },
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"source": "in", "target": "t1"},
            {"source": "t1", "target": "out"},
        ],
    }
    await client.post(
        f"/agents/{agent_id}/versions",
        json={"graph_json": graph},
        headers=auth_headers,
    )

    resp = await client.post(f"/agents/{agent_id}/publish", headers=auth_headers)
    assert resp.status_code == 400
