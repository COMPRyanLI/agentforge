"""Tool repository."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool
from app.schemas.tool import ToolCreate


class ToolRepo:
    async def create(self, session: AsyncSession, owner_id: uuid.UUID, data: ToolCreate) -> Tool:
        tool = Tool(
            owner_id=owner_id,
            name=data.name,
            description=data.description,
            json_schema=data.json_schema,
            impl_type=data.impl_type,
            config_json=data.config_json,
        )
        session.add(tool)
        await session.flush()
        await session.refresh(tool)
        return tool

    async def get(self, session: AsyncSession, tool_id: uuid.UUID) -> Tool | None:
        result = await session.execute(select(Tool).where(Tool.id == tool_id))
        return result.scalar_one_or_none()

    async def list_by_owner(self, session: AsyncSession, owner_id: uuid.UUID) -> list[Tool]:
        result = await session.execute(select(Tool).where(Tool.owner_id == owner_id))
        return list(result.scalars().all())

    async def update(self, session: AsyncSession, tool: Tool, **kwargs: Any) -> Tool:
        for key, value in kwargs.items():
            setattr(tool, key, value)
        await session.flush()
        await session.refresh(tool)
        return tool
