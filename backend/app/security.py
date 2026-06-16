"""Password hashing (pwdlib/bcrypt) and JWT signing (pyjwt)."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

if TYPE_CHECKING:
    from app.config import Settings

_hasher = PasswordHash((BcryptHasher(),))


def hash_password(plain: str) -> str:
    return str(_hasher.hash(plain))


def verify_password(plain: str, hashed: str) -> bool:
    return bool(_hasher.verify(plain, hashed))


def create_access_token(subject: str, settings: "Settings") -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return str(jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm))


def decode_access_token(token: str, settings: "Settings") -> str:
    """Decode a JWT and return the subject (user id).

    Raises HTTP 401 on invalid or expired tokens.
    """
    _401 = {"WWW-Authenticate": "Bearer"}
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        sub: str | None = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers=_401,
            )
        return sub
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers=_401,
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers=_401,
        ) from None
