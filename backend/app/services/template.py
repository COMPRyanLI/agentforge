"""Template service — listing and cloning starter graphs into new agents."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.template import Template
from app.repositories.agent import AgentRepo
from app.repositories.template import TemplateRepo

_repo = TemplateRepo()
_agent_repo = AgentRepo()


async def list_all(session: AsyncSession) -> list[Template]:
    return await _repo.list_all(session)


async def create_agent_from_template(
    session: AsyncSession, template_id: uuid.UUID, owner_id: uuid.UUID
) -> Agent:
    template = await _repo.get(session, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    agent = await _agent_repo.create(
        session, owner_id=owner_id, name=template.name, description=template.description
    )
    version = await _agent_repo.create_version(session, agent.id, template.graph_json)
    return await _agent_repo.set_current_version(session, agent, version)
