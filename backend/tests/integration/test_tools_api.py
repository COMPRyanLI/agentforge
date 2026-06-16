"""Integration tests for /tools endpoints."""

import pytest
from httpx import AsyncClient

_TOOL_PAYLOAD = {
    "name": "My Tool",
    "description": "A test tool",
    "json_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
    "impl_type": "http",
    "config_json": {"url": "https://example.com", "method": "GET"},
}


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "tool_user@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "other_tool_user@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_tool(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.post("/tools", json=_TOOL_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Tool"
    assert data["impl_type"] == "http"


async def test_list_tools_own_only(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    await client.post("/tools", json={**_TOOL_PAYLOAD, "name": "Alice Tool"}, headers=auth_headers)
    await client.post("/tools", json={**_TOOL_PAYLOAD, "name": "Bob Tool"}, headers=other_headers)

    resp = await client.get("/tools", headers=auth_headers)
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "Alice Tool" in names
    assert "Bob Tool" not in names


async def test_patch_tool_wrong_owner_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    create = await client.post("/tools", json=_TOOL_PAYLOAD, headers=auth_headers)
    tool_id = create.json()["id"]

    resp = await client.patch(
        f"/tools/{tool_id}",
        json={"name": "Hacked Name"},
        headers=other_headers,
    )
    assert resp.status_code == 403
