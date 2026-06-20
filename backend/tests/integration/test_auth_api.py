"""Integration tests for /auth endpoints."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    return resp.json()


async def test_register_returns_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/register",
        json={"email": "newuser@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_register_duplicate_returns_400(client: AsyncClient) -> None:
    payload = {"email": "dup@example.com", "password": "password123"}
    await client.post("/auth/register", json=payload)
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 400


async def test_login_returns_token(client: AsyncClient, registered_user: dict[str, str]) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


async def test_login_wrong_password_returns_401(
    client: AsyncClient, registered_user: dict[str, str]
) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_me_returns_current_user(
    client: AsyncClient, registered_user: dict[str, str]
) -> None:
    token = registered_user["access_token"]
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    # No Authorization header at all — FastAPI's HTTPBearer security dependency
    # rejects this before our own 401-on-bad-token logic ever runs.
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
