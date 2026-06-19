"""Marketplace router — discovery, install, and rating."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.agent import AgentRead
from app.schemas.marketplace import MarketplaceAgentRead, RatingCreate, RatingRead
from app.services import marketplace as marketplace_service

router = APIRouter(tags=["marketplace"])


@router.get("", response_model=list[MarketplaceAgentRead])
async def list_marketplace(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    q: str | None = None,
    sort: Annotated[str, Query(pattern="^(installs|rating)$")] = "installs",
) -> list[MarketplaceAgentRead]:
    agents = await marketplace_service.list_published(session, q, sort)
    return [MarketplaceAgentRead.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=MarketplaceAgentRead)
async def get_marketplace_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MarketplaceAgentRead:
    agent = await marketplace_service.get_published_or_404(session, agent_id)
    return MarketplaceAgentRead.model_validate(agent)


@router.get("/{agent_id}/ratings", response_model=list[RatingRead])
async def list_ratings(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[RatingRead]:
    ratings = await marketplace_service.list_ratings(session, agent_id)
    return [RatingRead.model_validate(r) for r in ratings]


@router.post("/{agent_id}/install", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def install_agent(
    agent_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentRead:
    clone = await marketplace_service.install(session, agent_id, current_user.id)
    return AgentRead.model_validate(clone)


@router.post("/{agent_id}/rate", response_model=RatingRead)
async def rate_agent(
    agent_id: uuid.UUID,
    data: RatingCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RatingRead:
    rating = await marketplace_service.rate(session, agent_id, current_user.id, data)
    return RatingRead.model_validate(rating)
