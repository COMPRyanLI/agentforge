"""Runs router — GET /runs/{run_id}."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.run import RunRead
from app.services import run as run_service

router = APIRouter(tags=["runs"])


@router.get("/{run_id}", response_model=RunRead)
async def get_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunRead:
    return await run_service.get_or_404(session, run_id, owner_id=current_user.id)
