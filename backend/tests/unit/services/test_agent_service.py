"""Unit tests for agent service with mocked AgentRepo."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services import agent as agent_service


def _make_agent(owner_id: uuid.UUID | None = None) -> Agent:
    return Agent(
        id=uuid.uuid4(),
        owner_id=owner_id or uuid.uuid4(),
        name="Test Agent",
        description=None,
        current_version_id=None,
        visibility="private",
        install_count=0,
        avg_rating=None,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


async def test_create_agent(mock_session: AsyncMock) -> None:
    owner_id = uuid.uuid4()
    new_agent = _make_agent(owner_id)
    with patch("app.services.agent._repo") as mock_repo:
        mock_repo.create = AsyncMock(return_value=new_agent)

        result = await agent_service.create(mock_session, owner_id, AgentCreate(name="Test Agent"))

    assert result is new_agent


async def test_get_or_404_not_found(mock_session: AsyncMock) -> None:
    with patch("app.services.agent._repo") as mock_repo:
        mock_repo.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await agent_service.get_or_404(mock_session, uuid.uuid4())
    assert exc_info.value.status_code == 404


async def test_get_or_404_wrong_owner(mock_session: AsyncMock) -> None:
    owner_id = uuid.uuid4()
    agent = _make_agent(owner_id)
    with patch("app.services.agent._repo") as mock_repo:
        mock_repo.get = AsyncMock(return_value=agent)

        with pytest.raises(HTTPException) as exc_info:
            await agent_service.get_or_404(mock_session, agent.id, owner_id=uuid.uuid4())
    assert exc_info.value.status_code == 403


async def test_update_agent(mock_session: AsyncMock) -> None:
    owner_id = uuid.uuid4()
    agent = _make_agent(owner_id)
    updated = _make_agent(owner_id)
    updated.name = "Updated Name"
    with patch("app.services.agent._repo") as mock_repo:
        mock_repo.get = AsyncMock(return_value=agent)
        mock_repo.update = AsyncMock(return_value=updated)

        result = await agent_service.update(
            mock_session, agent.id, owner_id, AgentUpdate(name="Updated Name")
        )
    assert result.name == "Updated Name"


async def test_publish_without_version_raises(mock_session: AsyncMock) -> None:
    owner_id = uuid.uuid4()
    agent = _make_agent(owner_id)
    with patch("app.services.agent._repo") as mock_repo:
        mock_repo.get = AsyncMock(return_value=agent)

        with pytest.raises(HTTPException) as exc_info:
            await agent_service.publish(mock_session, agent.id, owner_id)
    assert exc_info.value.status_code == 400
