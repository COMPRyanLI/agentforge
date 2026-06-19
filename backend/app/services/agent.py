"""Agent service — CRUD and publish logic."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentVersion
from app.repositories.agent import AgentRepo
from app.runtime.registry_builder import graph_references_db_backed_tool
from app.schemas.agent import AgentCreate, AgentUpdate, AgentVersionCreate

_repo = AgentRepo()


async def create(session: AsyncSession, owner_id: uuid.UUID, data: AgentCreate) -> Agent:
    return await _repo.create(
        session, owner_id=owner_id, name=data.name, description=data.description
    )


async def get_or_404(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
) -> Agent:
    agent = await _repo.get(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if owner_id is not None and agent.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your agent")
    return agent


async def list_mine(session: AsyncSession, owner_id: uuid.UUID) -> list[Agent]:
    return await _repo.list_by_owner(session, owner_id)


async def update(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: AgentUpdate,
) -> Agent:
    agent = await get_or_404(session, agent_id, owner_id)
    kwargs = data.model_dump(exclude_unset=True)
    if not kwargs:
        return agent
    return await _repo.update(session, agent, **kwargs)


async def create_version(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: AgentVersionCreate,
) -> AgentVersion:
    agent = await get_or_404(session, agent_id, owner_id)
    version = await _repo.create_version(session, agent.id, data.graph_json)
    await _repo.set_current_version(session, agent, version)
    return version


async def get_current_version(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> AgentVersion:
    agent = await get_or_404(session, agent_id, owner_id)
    if agent.current_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent has no saved version"
        )
    version = await _repo.get_version(session, agent.current_version_id)
    assert version is not None  # current_version_id always points at an existing version
    return version


async def publish(
    session: AsyncSession,
    agent_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> Agent:
    agent = await get_or_404(session, agent_id, owner_id)
    if agent.current_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish an agent with no versions",
        )
    version = await _repo.get_version(session, agent.current_version_id)
    assert version is not None  # current_version_id always points at an existing version
    if graph_references_db_backed_tool(version.graph_json):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish an agent that references a non-builtin tool",
        )
    return await _repo.publish(session, agent)
