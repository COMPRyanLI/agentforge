"""Unit tests for password hashing and JWT utilities."""

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.security import create_access_token, decode_access_token, hash_password, verify_password

_settings = Settings(secret_key="test-secret-key-for-unit-tests-32b")


def test_hash_and_verify() -> None:
    hashed = hash_password("mysecret")
    assert verify_password("mysecret", hashed) is True


def test_wrong_password_fails() -> None:
    hashed = hash_password("mysecret")
    assert verify_password("wrongpassword", hashed) is False


def test_create_and_decode_token() -> None:
    token = create_access_token("user-123", _settings)
    subject = decode_access_token(token, _settings)
    assert subject == "user-123"


def test_expired_token_raises() -> None:
    expired_settings = Settings(
        secret_key="test-secret-key-for-unit-tests-32b", jwt_expire_minutes=-1
    )
    token = create_access_token("user-123", expired_settings)
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, _settings)
    assert exc_info.value.status_code == 401


def test_invalid_token_raises() -> None:
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not.a.valid.jwt", _settings)
    assert exc_info.value.status_code == 401
