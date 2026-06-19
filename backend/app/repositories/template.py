"""Template repository — platform-provided starter graphs."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template


class TemplateRepo:
    async def list_all(self, session: AsyncSession) -> list[Template]:
        result = await session.execute(select(Template).order_by(Template.name))
        return list(result.scalars().all())

    async def get(self, session: AsyncSession, template_id: uuid.UUID) -> Template | None:
        result = await session.execute(select(Template).where(Template.id == template_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, session: AsyncSession, name: str) -> Template | None:
        result = await session.execute(select(Template).where(Template.name == name))
        return result.scalar_one_or_none()
