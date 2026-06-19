"""Templates router — listing platform-provided starter graphs."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.template import TemplateRead
from app.services import template as template_service

router = APIRouter(tags=["templates"])


@router.get("", response_model=list[TemplateRead])
async def list_templates(
    session: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[TemplateRead]:
    templates = await template_service.list_all(session)
    return [TemplateRead.model_validate(t) for t in templates]
