"""Tests for the secure create_user development/admin CLI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.cli import create_user as create_user_cli
from app.core.config import Settings, clear_settings_cache
from app.models.enums import UserRole, UserStatus
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.security.passwords import PasswordService
from app.security.tokens import hash_token
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_user_persists_and_hashes(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    email = f"create-{uuid.uuid4().hex[:10]}@example.com"
    password = "StrongCreateUserPass123!"

    code = await create_user_cli.create_user(
        email=f"  {email.upper()} ",
        full_name="  Local Admin ",
        role=UserRole.admin,
        password=password,
    )
    assert code == 0

    row = (await db_session.execute(select(User).where(User.email == email.lower()))).scalar_one()
    assert row.full_name == "Local Admin"
    assert row.role == UserRole.admin
    assert row.status == UserStatus.active
    assert PasswordService.from_settings(settings).verify_password(password, row.password_hash)
    assert not row.password_hash.startswith(password)


@pytest.mark.asyncio
async def test_create_user_refuses_duplicate(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    _ = settings
    email = f"dup-{uuid.uuid4().hex[:10]}@example.com"
    password = "StrongCreateUserPass123!"
    first = await create_user_cli.create_user(
        email=email,
        full_name="First",
        role=UserRole.user,
        password=password,
    )
    assert first == 0
    second = await create_user_cli.create_user(
        email=email,
        full_name="Second",
        role=UserRole.admin,
        password=password,
    )
    assert second == 1
    count = (
        await db_session.execute(select(func.count()).select_from(User).where(User.email == email))
    ).scalar_one()
    assert count == 1
    row = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert row.role == UserRole.user
    assert row.full_name == "First"


@pytest.mark.asyncio
async def test_create_user_refuses_weak_password(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    _ = db_session
    _ = settings
    code = await create_user_cli.create_user(
        email=f"weak-{uuid.uuid4().hex[:10]}@example.com",
        full_name="Weak",
        role=UserRole.user,
        password="short",
    )
    assert code == 1


@pytest.mark.asyncio
async def test_reset_password_revokes_sessions_without_role_change(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    email = f"reset-{uuid.uuid4().hex[:10]}@example.com"
    old_password = "OldCreateUserPass123!"
    new_password = "NewCreateUserPass123!"
    create_code = await create_user_cli.create_user(
        email=email,
        full_name="Reset Target",
        role=UserRole.admin,
        password=old_password,
    )
    assert create_code == 0

    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    now = datetime.now(UTC)
    session_row = RefreshSession(
        user_id=user.id,
        token_hash=hash_token("opaque-refresh-token-for-cli-test"),
        family_id=uuid.uuid4(),
        expires_at=now + timedelta(days=7),
        created_at=now,
        last_used_at=now,
    )
    db_session.add(session_row)
    await db_session.commit()

    reset_code = await create_user_cli.reset_existing_password(
        email=email,
        password=new_password,
    )
    assert reset_code == 0

    await db_session.refresh(user)
    await db_session.refresh(session_row)
    assert user.role == UserRole.admin
    assert user.status == UserStatus.active
    assert PasswordService.from_settings(settings).verify_password(new_password, user.password_hash)
    assert not PasswordService.from_settings(settings).verify_password(
        old_password, user.password_hash
    )
    assert session_row.revoked_at is not None


def test_main_password_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    _ = settings
    answers = iter(["one-password", "other-password"])
    monkeypatch.setattr(create_user_cli.getpass, "getpass", lambda _prompt: next(answers))
    code = create_user_cli.main(
        [
            "--email",
            "mismatch@example.com",
            "--name",
            "Mismatch",
            "--role",
            "user",
        ]
    )
    assert code == 1


def test_main_reset_password_rejects_name_or_role(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    _ = settings
    monkeypatch.setattr(create_user_cli.getpass, "getpass", lambda _prompt: "UnusedPass123!!!")
    code = create_user_cli.main(
        [
            "--email",
            "x@example.com",
            "--reset-password",
            "--role",
            "admin",
        ]
    )
    assert code == 1


def test_create_user_production_refuses(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    _ = settings
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PASSWORD_RESET_DEV_NOTICE_ENABLED", "false")
    monkeypatch.setenv("ADMIN_USER_CLI_ALLOW_PRODUCTION", "false")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "production-grade-cortexa-jwt-secret-key-at-least-32",
    )
    clear_settings_cache()
    try:
        code = create_user_cli.main(
            [
                "--email",
                "prod@example.com",
                "--name",
                "Prod",
                "--role",
                "admin",
            ]
        )
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("PASSWORD_RESET_DEV_NOTICE_ENABLED", "true")
        monkeypatch.setenv("ADMIN_USER_CLI_ALLOW_PRODUCTION", "false")
        clear_settings_cache()
    assert code == 2


def test_reset_password_via_create_user_refuses_production_even_with_override(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> None:
    _ = settings
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PASSWORD_RESET_DEV_NOTICE_ENABLED", "false")
    monkeypatch.setenv("ADMIN_USER_CLI_ALLOW_PRODUCTION", "true")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "production-grade-cortexa-jwt-secret-key-at-least-32",
    )
    clear_settings_cache()
    monkeypatch.setattr(
        create_user_cli.getpass,
        "getpass",
        lambda _prompt: "ShouldNeverBeUsed123!",
    )
    try:
        code = create_user_cli.main(
            [
                "--email",
                "prod-reset@example.com",
                "--reset-password",
            ]
        )
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv("PASSWORD_RESET_DEV_NOTICE_ENABLED", "true")
        monkeypatch.setenv("ADMIN_USER_CLI_ALLOW_PRODUCTION", "false")
        clear_settings_cache()
    assert code == 2
