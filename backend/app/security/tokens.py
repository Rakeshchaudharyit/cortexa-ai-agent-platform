"""JWT access-token and opaque refresh-token helpers."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.auth_exceptions import InvalidAccessTokenError
from app.core.config import Settings
from app.models.enums import UserRole

ACCESS_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class AccessTokenClaims:
    subject: uuid.UUID
    role: UserRole
    jti: str
    issued_at: datetime
    expires_at: datetime
    email: str | None = None


@dataclass(frozen=True)
class TokenService:
    """Issues and validates short-lived JWT access tokens."""

    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    @classmethod
    def from_settings(cls, settings: Settings) -> TokenService:
        return cls(
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
            access_token_expire_minutes=settings.access_token_expire_minutes,
        )

    def create_access_token(
        self,
        *,
        user_id: uuid.UUID,
        role: UserRole,
        email: str | None = None,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        issued_at = now or datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=self.access_token_expire_minutes)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "type": ACCESS_TOKEN_TYPE,
            "role": role.value,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid.uuid4()),
        }
        if email is not None:
            payload["email"] = email
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, expires_at

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={
                    "require": ["sub", "type", "role", "iat", "exp", "jti"],
                    "verify_signature": True,
                    "verify_exp": True,
                },
            )
        except InvalidTokenError as exc:
            raise InvalidAccessTokenError() from exc

        token_type = payload.get("type")
        if token_type != ACCESS_TOKEN_TYPE:
            raise InvalidAccessTokenError()

        subject_raw = payload.get("sub")
        if not subject_raw or not isinstance(subject_raw, str):
            raise InvalidAccessTokenError()
        try:
            subject = uuid.UUID(subject_raw)
        except ValueError as exc:
            raise InvalidAccessTokenError() from exc

        role_raw = payload.get("role")
        try:
            role = UserRole(str(role_raw))
        except ValueError as exc:
            raise InvalidAccessTokenError() from exc

        email = payload.get("email")
        if email is not None and not isinstance(email, str):
            raise InvalidAccessTokenError()

        return AccessTokenClaims(
            subject=subject,
            role=role,
            jti=str(payload["jti"]),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            email=email,
        )


def generate_refresh_token() -> str:
    """Return a cryptographically secure opaque refresh token."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Store only a SHA-256 digest of opaque tokens."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_optional_metadata(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
