"""Auth router — register and login."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.schemas.user import LoginRequest, Token, UserCreate
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Token:
    _, token = await auth_service.register(session, data, settings)
    return Token(access_token=token)


@router.post("/login", response_model=Token)
async def login(
    data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Token:
    _, token = await auth_service.login(session, data, settings)
    return Token(access_token=token)
