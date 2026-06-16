"""Agents router — CRUD, versioning, publish, and synchronous run."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user, get_llm_provider
from app.llm.provider import LLMProvider
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    AgentVersionCreate,
    AgentVersionRead,
)
from app.schemas.run import RunCreate, RunRead
from app.services import agent as agent_service
from app.services import run as run_service

router = APIRouter(tags=["agents"])


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    agent = await agent_service.create(session, current_user.id, data)
    return AgentRead.model_validate(agent)


@router.get("", response_model=list[AgentRead])
async def list_agents(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[AgentRead]:
    agents = await agent_service.list_mine(session, current_user.id)
    return [AgentRead.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    agent = await agent_service.get_or_404(session, agent_id, owner_id=current_user.id)
    return AgentRead.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: uuid.UUID,
    data: AgentUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    agent = await agent_service.update(session, agent_id, current_user.id, data)
    return AgentRead.model_validate(agent)


@router.post(
    "/{agent_id}/versions",
    response_model=AgentVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    agent_id: uuid.UUID,
    data: AgentVersionCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentVersionRead:
    version = await agent_service.create_version(session, agent_id, current_user.id, data)
    return AgentVersionRead.model_validate(version)


@router.post("/{agent_id}/publish", response_model=AgentRead)
async def publish_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    agent = await agent_service.publish(session, agent_id, current_user.id)
    return AgentRead.model_validate(agent)


@router.post("/{agent_id}/run", response_model=RunRead, status_code=status.HTTP_200_OK)
async def run_agent(
    agent_id: uuid.UUID,
    data: RunCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> RunRead:
    return await run_service.create_and_execute(session, agent_id, current_user.id, data, llm)
