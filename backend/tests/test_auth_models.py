"""Auth model and service-layer tests (PostgreSQL)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
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
from app.schemas.auth import normalize_email
from app.security.passwords import PasswordService
from app.security.tokens import hash_token
from app.services.auth import AuthService
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def auth_service(settings: Settings) -> AuthService:
    return AuthService.from_settings(settings)


def test_normalize_email() -> None:
    assert normalize_email("  Demo@Example.COM ") == "demo@example.com"


@pytest.mark.asyncio
async def test_user_creation_defaults(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    result = await auth_service.register(
        db_session,
        email="New.User@Example.com",
        password="StrongDemoPassword123!",
        full_name="New User",
    )
    user = await db_session.get(User, result.response.user.id)
    assert user is not None
    assert user.email == "new.user@example.com"
    assert user.role == UserRole.user
    assert user.status == UserStatus.active
    assert user.password_hash.startswith("$argon2")
    assert "StrongDemoPassword123!" not in user.password_hash


@pytest.mark.asyncio
async def test_case_insensitive_email_uniqueness(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    await auth_service.register(
        db_session,
        email="dup@example.com",
        password="StrongDemoPassword123!",
        full_name="One",
    )
    with pytest.raises(EmailAlreadyRegisteredError):
        await auth_service.register(
            db_session,
            email="DUP@example.com",
            password="StrongDemoPassword123!",
            full_name="Two",
        )


@pytest.mark.asyncio
async def test_token_hash_uniqueness_constraint(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    passwords = PasswordService.from_settings(settings)
    user = User(
        email="hash-unique@example.com",
        password_hash=passwords.hash_password("StrongDemoPassword123!"),
        full_name="Hash User",
    )
    db_session.add(user)
    await db_session.flush()
    digest = hash_token("same-token")
    first = RefreshSession(
        user_id=user.id,
        token_hash=digest,
        family_id=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(first)
    await db_session.flush()
    second = RefreshSession(
        user_id=user.id,
        token_hash=digest,
        family_id=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_login_updates_last_login(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    registered = await auth_service.register(
        db_session,
        email="login-ts@example.com",
        password="StrongDemoPassword123!",
        full_name="Login TS",
    )
    before = registered.response.user.last_login_at
    logged_in = await auth_service.login(
        db_session,
        email="login-ts@example.com",
        password="StrongDemoPassword123!",
    )
    assert logged_in.response.user.last_login_at is not None
    if before is not None:
        assert logged_in.response.user.last_login_at >= before


@pytest.mark.asyncio
async def test_login_unknown_email_generic(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    with pytest.raises(InvalidCredentialsError) as exc_info:
        await auth_service.login(
            db_session,
            email="missing@example.com",
            password="StrongDemoPassword123!",
        )
    assert exc_info.value.message == "Invalid email or password"


@pytest.mark.asyncio
async def test_login_wrong_password_generic(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    await auth_service.register(
        db_session,
        email="wrong-pw@example.com",
        password="StrongDemoPassword123!",
        full_name="Wrong PW",
    )
    with pytest.raises(InvalidCredentialsError) as exc_info:
        await auth_service.login(
            db_session,
            email="wrong-pw@example.com",
            password="TotallyWrongPassword!",
        )
    assert exc_info.value.message == "Invalid email or password"


@pytest.mark.asyncio
async def test_disabled_account_cannot_login(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    result = await auth_service.register(
        db_session,
        email="disabled-login@example.com",
        password="StrongDemoPassword123!",
        full_name="Disabled",
    )
    user = await db_session.get(User, result.response.user.id)
    assert user is not None
    user.status = UserStatus.disabled
    await db_session.commit()
    with pytest.raises(AccountDisabledError):
        await auth_service.login(
            db_session,
            email="disabled-login@example.com",
            password="StrongDemoPassword123!",
        )


@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse_detection(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    registered = await auth_service.register(
        db_session,
        email="rotate@example.com",
        password="StrongDemoPassword123!",
        full_name="Rotate",
    )
    old_raw = registered.refresh_token
    rotated = await auth_service.refresh(db_session, raw_refresh_token=old_raw)
    assert rotated.refresh_token != old_raw

    old_hash = hash_token(old_raw)
    old_session = (
        await db_session.execute(
            select(RefreshSession).where(RefreshSession.token_hash == old_hash)
        )
    ).scalar_one()
    assert old_session.revoked_at is not None
    assert old_session.replaced_by_session_id is not None

    with pytest.raises(RefreshTokenReuseDetectedError):
        await auth_service.refresh(db_session, raw_refresh_token=old_raw)

    family_sessions = (
        (
            await db_session.execute(
                select(RefreshSession).where(RefreshSession.family_id == old_session.family_id)
            )
        )
        .scalars()
        .all()
    )
    assert all(item.revoked_at is not None for item in family_sessions)


@pytest.mark.asyncio
async def test_expired_refresh_rejected(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    registered = await auth_service.register(
        db_session,
        email="expired-refresh@example.com",
        password="StrongDemoPassword123!",
        full_name="Expired",
    )
    digest = hash_token(registered.refresh_token)
    session_row = (
        await db_session.execute(select(RefreshSession).where(RefreshSession.token_hash == digest))
    ).scalar_one()
    session_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(RefreshTokenExpiredError):
        await auth_service.refresh(db_session, raw_refresh_token=registered.refresh_token)


@pytest.mark.asyncio
async def test_revoked_refresh_rejected(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    registered = await auth_service.register(
        db_session,
        email="revoked-refresh@example.com",
        password="StrongDemoPassword123!",
        full_name="Revoked",
    )
    await auth_service.logout(db_session, raw_refresh_token=registered.refresh_token)
    with pytest.raises((InvalidRefreshTokenError, RefreshTokenReuseDetectedError)):
        await auth_service.refresh(db_session, raw_refresh_token=registered.refresh_token)


@pytest.mark.asyncio
async def test_revoke_all_user_sessions(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    first = await auth_service.register(
        db_session,
        email="revoke-all@example.com",
        password="StrongDemoPassword123!",
        full_name="Revoke All",
    )
    second = await auth_service.login(
        db_session,
        email="revoke-all@example.com",
        password="StrongDemoPassword123!",
    )
    count = await auth_service.revoke_all_user_sessions(
        db_session,
        user_id=first.response.user.id,
    )
    assert count >= 1
    with pytest.raises((InvalidRefreshTokenError, RefreshTokenReuseDetectedError)):
        await auth_service.refresh(db_session, raw_refresh_token=second.refresh_token)


@pytest.mark.asyncio
async def test_disabled_user_cannot_refresh(
    db_session: AsyncSession,
    auth_service: AuthService,
) -> None:
    registered = await auth_service.register(
        db_session,
        email="disabled-refresh@example.com",
        password="StrongDemoPassword123!",
        full_name="Disabled Refresh",
    )
    user = await db_session.get(User, registered.response.user.id)
    assert user is not None
    user.status = UserStatus.disabled
    await db_session.commit()
    with pytest.raises(AccountDisabledError):
        await auth_service.refresh(db_session, raw_refresh_token=registered.refresh_token)
