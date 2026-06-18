"""Integration tests for /tools endpoints."""

import socket
from typing import Any

import httpx
import pytest
from httpx import AsyncClient

import app.runtime.http_tool as http_tool_module

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


async def test_test_tool_happy_path(
    client: AsyncClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_resolve(host: str, port: int) -> list[tuple[Any, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"q": dict(request.url.params).get("q")})

    def _fake_make_client(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False, timeout=timeout
        )

    monkeypatch.setattr(http_tool_module, "_resolve", _fake_resolve)
    monkeypatch.setattr(http_tool_module, "_make_client", _fake_make_client)

    create = await client.post("/tools", json=_TOOL_PAYLOAD, headers=auth_headers)
    tool_id = create.json()["id"]

    resp = await client.post(
        f"/tools/{tool_id}/test", json={"args": {"q": "hello"}}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["error"] is None
    assert data["result"] == {"q": "hello"}


async def test_test_tool_wrong_owner_returns_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    create = await client.post("/tools", json=_TOOL_PAYLOAD, headers=auth_headers)
    tool_id = create.json()["id"]

    resp = await client.post(f"/tools/{tool_id}/test", json={"args": {}}, headers=other_headers)
    assert resp.status_code == 403


async def test_test_tool_bad_args_returns_400(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    payload = {
        **_TOOL_PAYLOAD,
        "name": "Strict Tool",
        "json_schema": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
            "additionalProperties": False,
        },
    }
    create = await client.post("/tools", json=payload, headers=auth_headers)
    tool_id = create.json()["id"]

    resp = await client.post(f"/tools/{tool_id}/test", json={"args": {}}, headers=auth_headers)
    assert resp.status_code == 400
