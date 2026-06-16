"""Tools router — CRUD."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.tool import ToolCreate, ToolRead, ToolUpdate
from app.services import tool as tool_service

router = APIRouter(tags=["tools"])


@router.post("", response_model=ToolRead, status_code=status.HTTP_201_CREATED)
async def create_tool(
    data: ToolCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolRead:
    tool = await tool_service.create(session, current_user.id, data)
    return ToolRead.model_validate(tool)


@router.get("", response_model=list[ToolRead])
async def list_tools(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ToolRead]:
    tools = await tool_service.list_mine(session, current_user.id)
    return [ToolRead.model_validate(t) for t in tools]


@router.get("/{tool_id}", response_model=ToolRead)
async def get_tool(
    tool_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolRead:
    tool = await tool_service.get_or_404(session, tool_id, owner_id=current_user.id)
    return ToolRead.model_validate(tool)


@router.patch("/{tool_id}", response_model=ToolRead)
async def update_tool(
    tool_id: uuid.UUID,
    data: ToolUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolRead:
    tool = await tool_service.update(session, tool_id, current_user.id, data)
    return ToolRead.model_validate(tool)
