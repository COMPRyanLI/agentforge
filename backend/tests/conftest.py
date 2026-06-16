"""Shared test fixtures."""

import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Must be set before app.config is imported so get_settings() finds SECRET_KEY.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-min32b")

from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
