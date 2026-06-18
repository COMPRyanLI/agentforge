"""Integration test fixtures.

Provides a real Postgres DB (testcontainers locally, CI service via DATABASE_URL)
and an ASGI test client whose get_session dependency is overridden with a
per-test transaction that rolls back after each test.
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Iterator

# Ryuk (testcontainers reaper) cannot reliably bind its port on Windows Docker Desktop.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# psycopg's async mode (used by the LangGraph Postgres checkpointer) cannot run on
# Windows' default ProactorEventLoop; must set this before pytest-asyncio creates
# the session-scoped event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import app
from app.models import Base


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    url = os.environ.get("DATABASE_URL")
    if url:
        yield url
        return
    # testcontainers: requires Docker running locally
    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

        with PostgresContainer("postgres:16") as container:
            raw = container.get_connection_url()
            yield raw.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
                "psycopg2", "asyncpg"
            )
    except Exception as exc:
        pytest.skip(f"Docker not available for testcontainers: {exc}")


@pytest.fixture(scope="session")
async def db_engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    # NullPool: each checkout creates a fresh connection and releases it immediately,
    # preventing asyncpg connections from being shared across the per-test sessions
    # that run on the shared session-scoped event loop.
    engine = create_async_engine(db_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
