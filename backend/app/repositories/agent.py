"""Agent and AgentVersion repository."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentVersion


class AgentRepo:
    async def create(
        self,
        session: AsyncSession,
        owner_id: uuid.UUID,
        name: str,
        description: str | None,
    ) -> Agent:
        agent = Agent(owner_id=owner_id, name=name, description=description)
        session.add(agent)
        await session.flush()
        await session.refresh(agent)
        return agent

    async def get(self, session: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def list_by_owner(self, session: AsyncSession, owner_id: uuid.UUID) -> list[Agent]:
        result = await session.execute(select(Agent).where(Agent.owner_id == owner_id))
        return list(result.scalars().all())

    async def update(self, session: AsyncSession, agent: Agent, **kwargs: Any) -> Agent:
        for key, value in kwargs.items():
            setattr(agent, key, value)
        await session.flush()
        await session.refresh(agent)
        return agent

    async def create_version(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        graph_json: dict[str, Any],  # justified: graph shape is open-ended JSON
    ) -> AgentVersion:
        # Lock the agent row so concurrent requests for the same agent serialize here,
        # preventing duplicate version_numbers before the UNIQUE constraint fires.
        await session.execute(select(Agent).where(Agent.id == agent_id).with_for_update())
        max_result = await session.execute(
            select(func.coalesce(func.max(AgentVersion.version_number), 0)).where(
                AgentVersion.agent_id == agent_id
            )
        )
        version_number: int = max_result.scalar_one() + 1
        version = AgentVersion(
            agent_id=agent_id,
            version_number=version_number,
            graph_json=graph_json,
        )
        session.add(version)
        await session.flush()
        await session.refresh(version)
        return version

    async def get_version(
        self, session: AsyncSession, version_id: uuid.UUID
    ) -> AgentVersion | None:
        result = await session.execute(select(AgentVersion).where(AgentVersion.id == version_id))
        return result.scalar_one_or_none()

    async def set_current_version(
        self, session: AsyncSession, agent: Agent, version: AgentVersion
    ) -> Agent:
        agent.current_version_id = version.id
        await session.flush()
        await session.refresh(agent)
        return agent

    async def publish(self, session: AsyncSession, agent: Agent) -> Agent:
        agent.visibility = "published"
        await session.flush()
        await session.refresh(agent)
        return agent
