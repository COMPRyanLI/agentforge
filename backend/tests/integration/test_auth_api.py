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
