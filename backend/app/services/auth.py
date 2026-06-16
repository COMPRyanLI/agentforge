"""Auth service — register and login."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.user import User
from app.repositories.user import UserRepo
from app.schemas.user import LoginRequest, UserCreate
from app.security import create_access_token, hash_password, verify_password

_repo = UserRepo()


async def register(session: AsyncSession, data: UserCreate, settings: Settings) -> tuple[User, str]:
    existing = await _repo.get_by_email(session, data.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = await _repo.create(session, email=data.email, password_hash=hash_password(data.password))
    token = create_access_token(str(user.id), settings)
    return user, token


async def login(session: AsyncSession, data: LoginRequest, settings: Settings) -> tuple[User, str]:
    user = await _repo.get_by_email(session, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(str(user.id), settings)
    return user, token
