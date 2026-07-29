"""Password-reset service — forgot/reset flows, token lifecycle, session revocation."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.password_reset_exceptions import (
    PasswordResetDisabledError,
    PasswordResetPasswordMismatchError,
    PasswordResetTokenExpiredError,
    PasswordResetTokenInvalidError,
    PasswordResetTokenUsedError,
)
from app.models.enums import UserStatus
from app.models.password_reset import PasswordResetToken
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.notifications.base import PasswordResetMessage
from app.notifications.providers.development import (
    DevelopmentPasswordResetDelivery,
    build_reset_url,
)
from app.schemas.auth import normalize_email
from app.security.passwords import PasswordService
from app.security.tokens import hash_optional_metadata, hash_token

logger = logging.getLogger("cortexa.password_reset")

FORGOT_PASSWORD_MESSAGE = (
    "If an account exists for that email, password reset instructions have been prepared."
)
RESET_SUCCESS_MESSAGE = "Password reset successfully. You can now log in with your new password."


@dataclass
class PasswordResetService:
    """Orchestrates secure password-reset token issuance and consumption."""

    settings: Settings
    passwords: PasswordService
    delivery: DevelopmentPasswordResetDelivery
    redis: Any | None = None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        delivery: DevelopmentPasswordResetDelivery | None = None,
        redis: Any | None = None,
    ) -> PasswordResetService:
        from app.notifications.password_reset import create_password_reset_delivery

        return cls(
            settings=settings,
            passwords=PasswordService.from_settings(settings),
            delivery=delivery or create_password_reset_delivery(settings, redis=redis),
            redis=redis,
        )

    def _ensure_enabled(self) -> None:
        if not self.settings.password_reset_enabled:
            raise PasswordResetDisabledError()

    def generate_raw_token(self) -> str:
        return secrets.token_urlsafe(self.settings.password_reset_token_bytes)

    def hash_reset_token(self, raw_token: str) -> str:
        return hash_token(raw_token)

    def _privacy_hash(self, value: str, *, secret: str | None) -> str:
        material = (secret or self.settings.jwt_secret_key).encode("utf-8")
        return hmac.new(material, value.encode("utf-8"), hashlib.sha256).hexdigest()

    async def _cooldown_allows(
        self,
        *,
        email: str,
        ip_address: str | None,
    ) -> bool:
        """Return True when the request may proceed. Fail-open if Redis is unavailable."""
        cooldown = self.settings.password_reset_request_cooldown_seconds
        if cooldown <= 0:
            return True
        if self.redis is None:
            return True
        email_digest = self._privacy_hash(
            email,
            secret=self.settings.password_reset_ip_hash_secret,
        )
        ip_digest = self._privacy_hash(
            (ip_address or "unknown").strip() or "unknown",
            secret=self.settings.password_reset_ip_hash_secret,
        )
        key = f"cortexa:pwd_reset:cooldown:{email_digest}:{ip_digest}"
        try:
            created = await self.redis.set(key, "1", nx=True, ex=cooldown)
            return bool(created)
        except Exception:
            logger.warning("password_reset_cooldown_redis_unavailable fail_open=true")
            return True

    async def forgot_password(
        self,
        session: AsyncSession,
        *,
        email: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> str:
        """Always return the same safe message; never reveal account existence."""
        self._ensure_enabled()
        normalized = normalize_email(email)
        allowed = await self._cooldown_allows(email=normalized, ip_address=ip_address)
        if not allowed:
            logger.info("password_reset_forgot outcome=cooldown")
            return FORGOT_PASSWORD_MESSAGE

        user = await self._get_user_by_email(session, normalized)
        if user is None or user.status != UserStatus.active:
            logger.info("password_reset_forgot outcome=no_action")
            return FORGOT_PASSWORD_MESSAGE

        await self._enforce_active_token_limit(session, user_id=user.id)

        raw_token = self.generate_raw_token()
        token_digest = self.hash_reset_token(raw_token)
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.settings.password_reset_token_expire_minutes)
        row = PasswordResetToken(
            user_id=user.id,
            token_hash=token_digest,
            expires_at=expires_at,
            requested_ip_hash=self._metadata_hash(
                ip_address,
                secret=self.settings.password_reset_ip_hash_secret,
            ),
            user_agent_hash=self._metadata_hash(
                user_agent,
                secret=self.settings.password_reset_user_agent_hash_secret,
            ),
        )
        session.add(row)
        await session.flush()

        reset_url = build_reset_url(
            frontend_url=self.settings.password_reset_frontend_url,
            raw_token=raw_token,
        )
        try:
            await self.delivery.send_password_reset(
                PasswordResetMessage(
                    email=user.email,
                    reset_url=reset_url,
                    expires_at_iso=expires_at.isoformat(),
                )
            )
        except Exception:
            await session.rollback()
            logger.exception("password_reset_delivery_failed")
            # Enumeration-safe: still return the generic message; no token persisted.
            return FORGOT_PASSWORD_MESSAGE

        await session.commit()
        logger.info(
            "password_reset_forgot outcome=token_created user_id=%s expires_at=%s",
            user.id,
            expires_at.isoformat(),
        )
        return FORGOT_PASSWORD_MESSAGE

    async def reset_password(
        self,
        session: AsyncSession,
        *,
        raw_token: str,
        new_password: str,
        confirm_password: str,
    ) -> str:
        self._ensure_enabled()
        if new_password != confirm_password:
            raise PasswordResetPasswordMismatchError()

        token = raw_token.strip()
        if not token or len(token) > 512:
            raise PasswordResetTokenInvalidError()

        token_digest = self.hash_reset_token(token)
        now = datetime.now(UTC)

        result = await session.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == token_digest)
            .with_for_update()
        )
        reset_row = result.scalar_one_or_none()
        if reset_row is None:
            raise PasswordResetTokenInvalidError()
        if reset_row.revoked_at is not None:
            raise PasswordResetTokenInvalidError()
        if reset_row.used_at is not None:
            raise PasswordResetTokenUsedError()
        if reset_row.expires_at <= now:
            raise PasswordResetTokenExpiredError()

        user_result = await session.execute(
            select(User).where(User.id == reset_row.user_id).with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if user is None or user.status != UserStatus.active:
            raise PasswordResetTokenInvalidError()

        # Validate + hash with shared Argon2 policy (raises PasswordValidationError).
        new_hash = self.passwords.hash_password(new_password)
        user.password_hash = new_hash
        user.updated_at = now

        reset_row.used_at = now
        await self._revoke_other_reset_tokens(
            session,
            user_id=user.id,
            except_token_id=reset_row.id,
            now=now,
        )
        await self._revoke_refresh_sessions(session, user_id=user.id, now=now)
        await session.commit()
        logger.info("password_reset_success user_id=%s", user.id)
        return RESET_SUCCESS_MESSAGE

    async def admin_set_password(
        self,
        session: AsyncSession,
        *,
        email: str,
        new_password: str,
    ) -> User:
        """Development/admin CLI path — sets password and revokes sessions/tokens."""
        normalized = normalize_email(email)
        user = await self._get_user_by_email(session, normalized)
        if user is None:
            raise LookupError("user_not_found")
        now = datetime.now(UTC)
        user.password_hash = self.passwords.hash_password(new_password)
        user.updated_at = now
        await self._revoke_other_reset_tokens(
            session,
            user_id=user.id,
            except_token_id=None,
            now=now,
        )
        await self._revoke_refresh_sessions(session, user_id=user.id, now=now)
        await session.commit()
        logger.info("password_reset_admin_set user_id=%s", user.id)
        return user

    async def _enforce_active_token_limit(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> None:
        now = datetime.now(UTC)
        result = await session.execute(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .order_by(PasswordResetToken.created_at.asc())
        )
        active = list(result.scalars().all())
        max_active = self.settings.password_reset_max_active_tokens
        excess = len(active) - (max_active - 1)
        if excess <= 0:
            return
        for row in active[:excess]:
            row.revoked_at = now

    async def _revoke_other_reset_tokens(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        except_token_id: uuid.UUID | None,
        now: datetime,
    ) -> None:
        stmt = (
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        if except_token_id is not None:
            stmt = stmt.where(PasswordResetToken.id != except_token_id)
        await session.execute(stmt)

    async def _revoke_refresh_sessions(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        now: datetime,
    ) -> None:
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def _metadata_hash(self, value: str | None, *, secret: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if secret:
            return self._privacy_hash(normalized, secret=secret)
        return hash_optional_metadata(normalized)

    async def _get_user_by_email(self, session: AsyncSession, email: str) -> User | None:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
