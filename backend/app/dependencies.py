"""FastAPI dependency providers for auth, settings, and infrastructure."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.llm.provider import LLMProvider, OllamaProvider
from app.models.user import User
from app.repositories.user import UserRepo
from app.runtime.checkpointer import get_checkpointer as _get_checkpointer
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


async def get_optional_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> "User | None":
    """Like get_current_user but returns None instead of raising when credentials are absent.

    Used by the SSE endpoint which also accepts a ?token= query param (EventSource can't
    send custom headers).
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token_str = auth_header[7:]
    try:
        subject = decode_access_token(token_str, settings)
        user_id = uuid.UUID(subject)
    except (HTTPException, ValueError):
        return None
    return await _user_repo.get_by_id(session, user_id)


async def get_arq_pool(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[ArqRedis]:
    """Yield an arq Redis pool for job enqueueing; closed after the request."""
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        yield pool
    finally:
        await pool.aclose()


async def get_redis(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[Redis]:
    """Yield a redis.asyncio client for pub/sub (SSE endpoint); closed after request."""
    client: Redis = Redis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.aclose()


async def get_checkpointer() -> AsyncPostgresSaver:
    """Provide the process-wide checkpointer for reading checkpoint history (replay).

    Lazily created on first use, same singleton pattern as app/db.py's engine —
    not closed per-request since the pool is long-lived for the app process.
    """
    return await _get_checkpointer()
