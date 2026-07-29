"""Authentication service — registration, login, refresh rotation, logout."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth_exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    RefreshTokenExpiredError,
    RefreshTokenReuseDetectedError,
)
from app.core.config import Settings
from app.models.enums import UserRole, UserStatus
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.schemas.auth import AuthTokenResponse, UserPublic, normalize_email
from app.security.passwords import PasswordService
from app.security.tokens import (
    TokenService,
    generate_refresh_token,
    hash_optional_metadata,
    hash_token,
)

logger = logging.getLogger("cortexa.auth")


@dataclass(frozen=True)
class AuthResult:
    response: AuthTokenResponse
    refresh_token: str
    refresh_expires_at: datetime


@dataclass
class AuthService:
    """Orchestrates user authentication and refresh-session lifecycle."""

    settings: Settings
    passwords: PasswordService
    tokens: TokenService

    @classmethod
    def from_settings(cls, settings: Settings) -> AuthService:
        return cls(
            settings=settings,
            passwords=PasswordService.from_settings(settings),
            tokens=TokenService.from_settings(settings),
        )

    async def register(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        full_name: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthResult:
        normalized = normalize_email(email)
        password_hash = self.passwords.hash_password(password)
        user = User(
            email=normalized,
            password_hash=password_hash,
            full_name=full_name.strip(),
            role=UserRole.user,
            status=UserStatus.active,
            is_email_verified=False,
        )
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            logger.info("registration_failed outcome=duplicate_email")
            raise EmailAlreadyRegisteredError() from exc

        result = await self._issue_auth_result(
            session,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            update_last_login=True,
        )
        await session.commit()
        logger.info("registration_success user_id=%s", user.id)
        return result

    async def login(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthResult:
        normalized = normalize_email(email)
        user = await self._get_user_by_email(session, normalized)
        if user is None:
            # Constant-time-ish dummy verify against a valid hash format is not
            # required here; never reveal whether the email exists.
            logger.info("login_failed outcome=invalid_credentials")
            raise InvalidCredentialsError()

        if not self.passwords.verify_password(password, user.password_hash):
            logger.info("login_failed outcome=invalid_credentials user_id=%s", user.id)
            raise InvalidCredentialsError()

        if user.status != UserStatus.active:
            logger.info("login_failed outcome=account_disabled user_id=%s", user.id)
            raise AccountDisabledError()

        result = await self._issue_auth_result(
            session,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            update_last_login=True,
        )
        await session.commit()
        logger.info("login_success user_id=%s", user.id)
        return result

    async def refresh(
        self,
        session: AsyncSession,
        *,
        raw_refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthResult:
        token_digest = hash_token(raw_refresh_token)
        refresh_session = await self._get_session_by_hash(session, token_digest)
        if refresh_session is None:
            logger.info("refresh_failed outcome=invalid_token")
            raise InvalidRefreshTokenError()

        now = datetime.now(UTC)
        if refresh_session.revoked_at is not None:
            await self._revoke_family(session, refresh_session.family_id, now=now)
            await session.commit()
            logger.warning(
                "refresh_token_reuse_detected user_id=%s family_id=%s",
                refresh_session.user_id,
                refresh_session.family_id,
            )
            raise RefreshTokenReuseDetectedError()

        if refresh_session.expires_at <= now:
            refresh_session.revoked_at = now
            await session.commit()
            logger.info("refresh_failed outcome=expired user_id=%s", refresh_session.user_id)
            raise RefreshTokenExpiredError()

        user = refresh_session.user
        if user is None:
            user = await session.get(User, refresh_session.user_id)
        if user is None:
            raise InvalidRefreshTokenError()
        if user.status != UserStatus.active:
            await self._revoke_family(session, refresh_session.family_id, now=now)
            await session.commit()
            logger.info("refresh_failed outcome=account_disabled user_id=%s", user.id)
            raise AccountDisabledError()

        # Rotate: revoke current, create replacement in same family.
        new_raw = generate_refresh_token()
        new_session = RefreshSession(
            user_id=user.id,
            token_hash=hash_token(new_raw),
            family_id=refresh_session.family_id,
            expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
            user_agent_hash=hash_optional_metadata(user_agent),
            ip_address_hash=hash_optional_metadata(ip_address),
            last_used_at=now,
        )
        session.add(new_session)
        await session.flush()

        refresh_session.revoked_at = now
        refresh_session.replaced_by_session_id = new_session.id
        refresh_session.last_used_at = now

        access_token, access_expires = self.tokens.create_access_token(
            user_id=user.id,
            role=user.role,
            email=user.email,
            now=now,
        )
        response = AuthTokenResponse(
            user=UserPublic.model_validate(user),
            access_token=access_token,
            token_type="bearer",
            expires_in=self.settings.access_token_expire_minutes * 60,
            access_token_expires_at=access_expires,
        )
        await session.commit()
        logger.info("refresh_success user_id=%s", user.id)
        return AuthResult(
            response=response,
            refresh_token=new_raw,
            refresh_expires_at=new_session.expires_at,
        )

    async def logout(
        self,
        session: AsyncSession,
        *,
        raw_refresh_token: str | None,
    ) -> None:
        if not raw_refresh_token:
            logger.info("logout_success outcome=no_cookie")
            return
        token_digest = hash_token(raw_refresh_token)
        refresh_session = await self._get_session_by_hash(session, token_digest)
        if refresh_session is None:
            logger.info("logout_success outcome=unknown_session")
            return
        if refresh_session.revoked_at is None:
            refresh_session.revoked_at = datetime.now(UTC)
            await session.commit()
        logger.info("logout_success user_id=%s", refresh_session.user_id)

    async def revoke_all_user_sessions(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> int:
        """Revoke every active refresh session for a user (service-layer only)."""
        now = datetime.now(UTC)
        result = await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await session.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    async def get_user_by_id(self, session: AsyncSession, user_id: uuid.UUID) -> User | None:
        return await session.get(User, user_id)

    def ensure_active(self, user: User) -> User:
        if user.status != UserStatus.active:
            logger.info("auth_rejected outcome=account_disabled user_id=%s", user.id)
            raise AccountDisabledError()
        return user

    async def _issue_auth_result(
        self,
        session: AsyncSession,
        *,
        user: User,
        user_agent: str | None,
        ip_address: str | None,
        update_last_login: bool,
    ) -> AuthResult:
        now = datetime.now(UTC)
        if update_last_login:
            user.last_login_at = now
            user.updated_at = now

        raw_refresh = generate_refresh_token()
        refresh_session = RefreshSession(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            family_id=uuid.uuid4(),
            expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
            user_agent_hash=hash_optional_metadata(user_agent),
            ip_address_hash=hash_optional_metadata(ip_address),
            last_used_at=now,
        )
        session.add(refresh_session)
        await session.flush()

        access_token, access_expires = self.tokens.create_access_token(
            user_id=user.id,
            role=user.role,
            email=user.email,
            now=now,
        )
        response = AuthTokenResponse(
            user=UserPublic.model_validate(user),
            access_token=access_token,
            token_type="bearer",
            expires_in=self.settings.access_token_expire_minutes * 60,
            access_token_expires_at=access_expires,
        )
        return AuthResult(
            response=response,
            refresh_token=raw_refresh,
            refresh_expires_at=refresh_session.expires_at,
        )

    async def _get_user_by_email(self, session: AsyncSession, email: str) -> User | None:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_session_by_hash(
        self,
        session: AsyncSession,
        token_digest: str,
    ) -> RefreshSession | None:
        result = await session.execute(
            select(RefreshSession)
            .options(selectinload(RefreshSession.user))
            .where(RefreshSession.token_hash == token_digest)
        )
        return result.scalar_one_or_none()

    async def _revoke_family(
        self,
        session: AsyncSession,
        family_id: uuid.UUID,
        *,
        now: datetime,
    ) -> None:
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
