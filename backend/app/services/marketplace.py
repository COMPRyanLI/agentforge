"""Marketplace service — discovery, install (clone), and rating logic."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.marketplace import Rating
from app.repositories.agent import AgentRepo
from app.repositories.marketplace import MarketplaceRepo
from app.runtime.registry_builder import graph_references_db_backed_tool
from app.schemas.marketplace import RatingCreate

_repo = MarketplaceRepo()
_agent_repo = AgentRepo()


async def list_published(session: AsyncSession, q: str | None, sort: str) -> list[Agent]:
    return await _repo.list_published(session, q, sort)


async def get_published_or_404(session: AsyncSession, agent_id: uuid.UUID) -> Agent:
    agent = await _repo.get_published(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def list_ratings(session: AsyncSession, agent_id: uuid.UUID) -> list[Rating]:
    await get_published_or_404(session, agent_id)
    return await _repo.list_ratings(session, agent_id)


async def rate(
    session: AsyncSession,
    agent_id: uuid.UUID,
    user_id: uuid.UUID,
    data: RatingCreate,
) -> Rating:
    agent = await get_published_or_404(session, agent_id)
    if agent.owner_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot rate your own agent",
        )
    rating = await _repo.upsert_rating(session, agent_id, user_id, data.score, data.comment)
    await _repo.recompute_avg_rating(session, agent_id)
    return rating


async def install(session: AsyncSession, agent_id: uuid.UUID, user_id: uuid.UUID) -> Agent:
    agent = await get_published_or_404(session, agent_id)
    if agent.current_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent has no version to install",
        )
    version = await _agent_repo.get_version(session, agent.current_version_id)
    assert version is not None  # current_version_id always points at an existing version
    # Defense in depth: publish() already rejects non-builtin-tool graphs, but
    # current_version_id can move after publish (saving a new draft re-points
    # it without re-running the gate) — re-check the exact graph being cloned.
    if graph_references_db_backed_tool(version.graph_json):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent's current version references a non-builtin tool and cannot be installed",
        )

    clone = await _agent_repo.create(
        session, owner_id=user_id, name=agent.name, description=agent.description
    )
    clone_version = await _agent_repo.create_version(session, clone.id, version.graph_json)
    clone = await _agent_repo.set_current_version(session, clone, clone_version)

    await _repo.record_install(session, agent_id, user_id)
    await _repo.increment_install_count(session, agent_id)
    return clone
