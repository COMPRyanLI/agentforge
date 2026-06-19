"""Marketplace repository: published-agent discovery, ratings, installs."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.marketplace import Install, Rating


class MarketplaceRepo:
    async def list_published(self, session: AsyncSession, q: str | None, sort: str) -> list[Agent]:
        stmt = select(Agent).where(Agent.visibility == "published")
        if q:
            stmt = stmt.where(Agent.name.ilike(f"%{q}%"))
        if sort == "rating":
            stmt = stmt.order_by(Agent.avg_rating.desc())
        else:
            stmt = stmt.order_by(Agent.install_count.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_published(self, session: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
        result = await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.visibility == "published")
        )
        return result.scalar_one_or_none()

    async def upsert_rating(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        user_id: uuid.UUID,
        score: int,
        comment: str | None,
    ) -> Rating:
        result = await session.execute(
            select(Rating).where(Rating.agent_id == agent_id, Rating.user_id == user_id)
        )
        rating = result.scalar_one_or_none()
        if rating is None:
            rating = Rating(agent_id=agent_id, user_id=user_id, score=score, comment=comment)
            session.add(rating)
        else:
            rating.score = score
            rating.comment = comment
        await session.flush()
        await session.refresh(rating)
        return rating

    async def list_ratings(self, session: AsyncSession, agent_id: uuid.UUID) -> list[Rating]:
        result = await session.execute(
            select(Rating).where(Rating.agent_id == agent_id).order_by(Rating.created_at.desc())
        )
        return list(result.scalars().all())

    async def recompute_avg_rating(self, session: AsyncSession, agent_id: uuid.UUID) -> None:
        avg_result = await session.execute(
            select(func.coalesce(func.avg(Rating.score), 0.0)).where(Rating.agent_id == agent_id)
        )
        avg_score = avg_result.scalar_one()
        await session.execute(
            update(Agent).where(Agent.id == agent_id).values(avg_rating=avg_score)
        )

    async def record_install(
        self, session: AsyncSession, agent_id: uuid.UUID, user_id: uuid.UUID
    ) -> Install:
        install = Install(agent_id=agent_id, user_id=user_id)
        session.add(install)
        await session.flush()
        await session.refresh(install)
        return install

    async def increment_install_count(self, session: AsyncSession, agent_id: uuid.UUID) -> None:
        # Atomic SQL-level increment — a Python read-modify-write on a loaded
        # Agent would lose updates under concurrent installs (same race the
        # version-number fix in AgentRepo.create_version guards against).
        await session.execute(
            update(Agent).where(Agent.id == agent_id).values(install_count=Agent.install_count + 1)
        )
