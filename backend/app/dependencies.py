"""FastAPI dependency providers for auth, settings, and infrastructure."""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.llm.provider import LLMProvider, OllamaProvider
from app.models.user import User
from app.repositories.user import UserRepo
from app.security import decode_access_token

_http_bearer = HTTPBearer()

_user_repo = UserRepo()


def get_llm_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LLMProvider:
    """Provide the configured LLMProvider.

    Extracted as a FastAPI dependency so tests can override it with a mock
    without requiring a live Ollama instance.
    """
    return OllamaProvider(settings.ollama_base_url, settings.ollama_model)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_http_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    subject = decode_access_token(credentials.credentials, settings)
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    user = await _user_repo.get_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
