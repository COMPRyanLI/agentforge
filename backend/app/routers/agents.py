"""Agents router — CRUD, versioning, publish, and async run."""

import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_arq_pool, get_current_user
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    AgentVersionCreate,
    AgentVersionRead,
)
from app.schemas.run import AgentRunStats, RunCreate, RunEnqueueResponse, RunRead
from app.services import agent as agent_service
from app.services import run as run_service
from app.services import template as template_service

router = APIRouter(tags=["agents"])


@router.post(
    "/from-template/{template_id}",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_from_template(
    template_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    agent = await template_service.create_agent_from_template(session, template_id, current_user.id)
    return AgentRead.model_validate(agent)


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


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await agent_service.delete(session, agent_id, current_user.id)


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


@router.get("/{agent_id}/versions/current", response_model=AgentVersionRead)
async def get_current_version(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentVersionRead:
    version = await agent_service.get_current_version(session, agent_id, current_user.id)
    return AgentVersionRead.model_validate(version)


@router.post("/{agent_id}/publish", response_model=AgentRead)
async def publish_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    agent = await agent_service.publish(session, agent_id, current_user.id)
    return AgentRead.model_validate(agent)


@router.post(
    "/{agent_id}/run",
    response_model=RunEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_agent(
    agent_id: uuid.UUID,
    data: RunCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> RunEnqueueResponse:
    response = await run_service.create_pending(session, agent_id, current_user.id, data)
    await arq_pool.enqueue_job("execute_run", str(response.run_id))
    return response


@router.get("/{agent_id}/runs", response_model=list[RunRead])
async def list_agent_runs(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[RunRead]:
    return await run_service.list_by_agent(session, agent_id, current_user.id)


@router.get("/{agent_id}/runs/stats", response_model=AgentRunStats)
async def get_agent_run_stats(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRunStats:
    return await run_service.get_agent_stats(session, agent_id, current_user.id)
