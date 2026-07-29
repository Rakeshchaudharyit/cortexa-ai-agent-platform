"""JWT access-token unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.auth_exceptions import InvalidAccessTokenError
from app.core.config import Settings
from app.models.enums import UserRole
from app.security.tokens import ACCESS_TOKEN_TYPE, TokenService, hash_token


@pytest.fixture
def tokens(settings: Settings) -> TokenService:
    return TokenService.from_settings(settings)


def test_create_and_decode_access_token(tokens: TokenService) -> None:
    user_id = uuid.uuid4()
    token, expires = tokens.create_access_token(
        user_id=user_id,
        role=UserRole.user,
        email="demo@example.com",
    )
    claims = tokens.decode_access_token(token)
    assert claims.subject == user_id
    assert claims.role == UserRole.user
    assert claims.email == "demo@example.com"
    assert claims.expires_at.replace(microsecond=0) == expires.replace(microsecond=0)
    assert claims.jti


def test_expired_access_token_rejected(tokens: TokenService, settings: Settings) -> None:
    user_id = uuid.uuid4()
    now = datetime.now(UTC) - timedelta(hours=2)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "role": UserRole.user.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=1)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidAccessTokenError):
        tokens.decode_access_token(token)


def test_invalid_signature_rejected(tokens: TokenService) -> None:
    user_id = uuid.uuid4()
    token, _ = tokens.create_access_token(user_id=user_id, role=UserRole.user)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(InvalidAccessTokenError):
        tokens.decode_access_token(tampered)


def test_wrong_token_type_rejected(tokens: TokenService, settings: Settings) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "refresh",
        "role": UserRole.user.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidAccessTokenError):
        tokens.decode_access_token(token)


def test_missing_subject_rejected(tokens: TokenService, settings: Settings) -> None:
    now = datetime.now(UTC)
    payload = {
        "type": ACCESS_TOKEN_TYPE,
        "role": UserRole.user.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidAccessTokenError):
        tokens.decode_access_token(token)


def test_alg_none_rejected(tokens: TokenService) -> None:
    now = datetime.now(UTC)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": ACCESS_TOKEN_TYPE,
        "role": UserRole.user.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    # Manually craft an unsigned token to avoid relying on jwt.encode(alg=none).
    import base64
    import json

    def b64url(data: dict[str, object]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    token = f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url(payload)}."
    with pytest.raises(InvalidAccessTokenError):
        tokens.decode_access_token(token)


def test_refresh_token_hash_is_digest_not_raw() -> None:
    raw = "opaque-refresh-token-value"
    digest = hash_token(raw)
    assert digest != raw
    assert len(digest) == 64
    assert raw not in digest
