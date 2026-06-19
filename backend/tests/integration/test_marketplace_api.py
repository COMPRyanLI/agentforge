"""Integration tests for /marketplace endpoints."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "publisher@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/register",
        json={"email": "installer@example.com", "password": "password123"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _publish_agent(
    client: AsyncClient, headers: dict[str, str], name: str = "Published Agent"
) -> str:
    create = await client.post("/agents", json={"name": name}, headers=headers)
    agent_id = create.json()["id"]
    graph = {
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
    await client.post(f"/agents/{agent_id}/versions", json={"graph_json": graph}, headers=headers)
    await client.post(f"/agents/{agent_id}/publish", headers=headers)
    return str(agent_id)


async def test_published_agent_appears_in_marketplace(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    agent_id = await _publish_agent(client, auth_headers)
    resp = await client.get("/marketplace", headers=auth_headers)
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.json()]
    assert agent_id in ids


async def test_private_agent_not_in_marketplace(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    create = await client.post("/agents", json={"name": "Private Agent"}, headers=auth_headers)
    agent_id = create.json()["id"]

    resp = await client.get("/marketplace", headers=auth_headers)
    ids = [a["id"] for a in resp.json()]
    assert agent_id not in ids

    detail = await client.get(f"/marketplace/{agent_id}", headers=auth_headers)
    assert detail.status_code == 404


async def test_install_clones_agent_and_increments_count(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    agent_id = await _publish_agent(client, auth_headers)

    resp = await client.post(f"/marketplace/{agent_id}/install", headers=other_headers)
    assert resp.status_code == 201
    clone = resp.json()
    assert clone["id"] != agent_id
    assert clone["visibility"] == "private"

    # The clone is owned by the installer and has a runnable version.
    mine = await client.get(f"/agents/{clone['id']}", headers=other_headers)
    assert mine.status_code == 200
    assert mine.json()["current_version_id"] is not None

    detail = await client.get(f"/marketplace/{agent_id}", headers=other_headers)
    assert detail.json()["install_count"] == 1

    # A second install by the same user creates another clone and increments again.
    resp2 = await client.post(f"/marketplace/{agent_id}/install", headers=other_headers)
    assert resp2.json()["id"] != clone["id"]
    detail2 = await client.get(f"/marketplace/{agent_id}", headers=other_headers)
    assert detail2.json()["install_count"] == 2


async def test_rate_then_rerate_updates_instead_of_duplicating(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    agent_id = await _publish_agent(client, auth_headers)

    resp = await client.post(
        f"/marketplace/{agent_id}/rate",
        json={"score": 3, "comment": "ok"},
        headers=other_headers,
    )
    assert resp.status_code == 200

    detail = await client.get(f"/marketplace/{agent_id}", headers=other_headers)
    assert detail.json()["avg_rating"] == 3.0

    resp2 = await client.post(
        f"/marketplace/{agent_id}/rate",
        json={"score": 5, "comment": "great"},
        headers=other_headers,
    )
    assert resp2.status_code == 200

    detail2 = await client.get(f"/marketplace/{agent_id}", headers=other_headers)
    assert detail2.json()["avg_rating"] == 5.0

    ratings = await client.get(f"/marketplace/{agent_id}/ratings", headers=other_headers)
    assert len(ratings.json()) == 1


async def test_owner_cannot_rate_own_agent(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    agent_id = await _publish_agent(client, auth_headers)
    resp = await client.post(
        f"/marketplace/{agent_id}/rate",
        json={"score": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 403


async def test_zero_ratings_reports_zero_not_null(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    agent_id = await _publish_agent(client, auth_headers)
    detail = await client.get(f"/marketplace/{agent_id}", headers=auth_headers)
    assert detail.json()["avg_rating"] == 0.0


async def test_search_and_sort(
    client: AsyncClient, auth_headers: dict[str, str], other_headers: dict[str, str]
) -> None:
    alpha_id = await _publish_agent(client, auth_headers, name="Alpha Helper")
    beta_id = await _publish_agent(client, auth_headers, name="Beta Helper")

    await client.post(f"/marketplace/{alpha_id}/install", headers=other_headers)
    await client.post(f"/marketplace/{alpha_id}/install", headers=other_headers)
    await client.post(f"/marketplace/{beta_id}/install", headers=other_headers)

    search = await client.get("/marketplace", params={"q": "Alpha"}, headers=auth_headers)
    names = [a["name"] for a in search.json()]
    assert names == ["Alpha Helper"]

    sorted_by_installs = await client.get(
        "/marketplace", params={"sort": "installs"}, headers=auth_headers
    )
    ids_in_order = [a["id"] for a in sorted_by_installs.json()]
    assert ids_in_order.index(alpha_id) < ids_in_order.index(beta_id)
