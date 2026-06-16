"""Tool service — CRUD logic."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool import Tool
from app.repositories.tool import ToolRepo
from app.schemas.tool import ToolCreate, ToolUpdate

_repo = ToolRepo()


async def create(session: AsyncSession, owner_id: uuid.UUID, data: ToolCreate) -> Tool:
    return await _repo.create(session, owner_id=owner_id, data=data)


async def get_or_404(
    session: AsyncSession,
    tool_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
) -> Tool:
    tool = await _repo.get(session, tool_id)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    if owner_id is not None and tool.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your tool")
    return tool


async def list_mine(session: AsyncSession, owner_id: uuid.UUID) -> list[Tool]:
    return await _repo.list_by_owner(session, owner_id)


async def update(
    session: AsyncSession,
    tool_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: ToolUpdate,
) -> Tool:
    tool = await get_or_404(session, tool_id, owner_id)
    kwargs = data.model_dump(exclude_unset=True)
    if not kwargs:
        return tool
    return await _repo.update(session, tool, **kwargs)
