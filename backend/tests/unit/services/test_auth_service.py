"""Unit tests for auth service with mocked UserRepo."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.models.user import User
from app.schemas.user import LoginRequest, UserCreate
from app.security import hash_password
from app.services import auth as auth_service

_settings = Settings(secret_key="test-secret-key-for-unit-tests-32b")


def _make_user(email: str = "test@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash=hash_password("password123"),
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


async def test_register_success(mock_session: AsyncMock) -> None:
    with patch("app.services.auth._repo") as mock_repo:
        mock_repo.get_by_email = AsyncMock(return_value=None)
        new_user = _make_user()
        mock_repo.create = AsyncMock(return_value=new_user)

        user, token = await auth_service.register(
            mock_session, UserCreate(email="test@example.com", password="password123"), _settings
        )

    assert user is new_user
    assert isinstance(token, str)


async def test_register_duplicate_email_raises(mock_session: AsyncMock) -> None:
    with patch("app.services.auth._repo") as mock_repo:
        mock_repo.get_by_email = AsyncMock(return_value=_make_user())

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.register(
                mock_session,
                UserCreate(email="test@example.com", password="password123"),
                _settings,
            )
    assert exc_info.value.status_code == 400


async def test_login_success(mock_session: AsyncMock) -> None:
    existing = _make_user()
    with patch("app.services.auth._repo") as mock_repo:
        mock_repo.get_by_email = AsyncMock(return_value=existing)

        user, token = await auth_service.login(
            mock_session, LoginRequest(email="test@example.com", password="password123"), _settings
        )

    assert user is existing
    assert isinstance(token, str)


async def test_login_bad_password_raises(mock_session: AsyncMock) -> None:
    existing = _make_user()
    with patch("app.services.auth._repo") as mock_repo:
        mock_repo.get_by_email = AsyncMock(return_value=existing)

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login(
                mock_session,
                LoginRequest(email="test@example.com", password="wrongpassword"),
                _settings,
            )
    assert exc_info.value.status_code == 401


async def test_login_unknown_email_raises(mock_session: AsyncMock) -> None:
    with patch("app.services.auth._repo") as mock_repo:
        mock_repo.get_by_email = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login(
                mock_session,
                LoginRequest(email="nobody@example.com", password="password123"),
                _settings,
            )
    assert exc_info.value.status_code == 401
