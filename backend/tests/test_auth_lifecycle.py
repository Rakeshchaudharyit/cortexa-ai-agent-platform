"""Authentication lifecycle + persistence regression tests (isolated test DB only)."""

from __future__ import annotations

import uuid

import pytest
from app.core.config import Settings
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.db.test_safety import assert_safe_test_session
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.security.passwords import PasswordService
from app.services.auth import AuthService
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

STRONG_PASSWORD = "StrongDemoPassword123!"


def _email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


@pytest.mark.asyncio
async def test_register_persists_user_readable_in_fresh_session(
    auth_client: AsyncClient,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    email = _email("reg-persist")
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
            "full_name": "Persist Reg",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]
    assert response.json()["access_token"]
    assert settings.auth_cookie_name in response.cookies

    row = (await db_session.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one()
    assert row.email == email.lower()
    assert row.status.value == "active"
    assert row.role.value == "user"
    assert row.password_hash.startswith("$argon2id$")
    assert PasswordService.from_settings(settings).verify_password(
        STRONG_PASSWORD, row.password_hash
    )

    refresh_count = (
        await db_session.execute(
            select(func.count()).select_from(RefreshSession).where(RefreshSession.user_id == row.id)
        )
    ).scalar_one()
    assert refresh_count >= 1

    # Fresh ORM session after dispose still sees the committed user.
    await dispose_engine()
    init_engine(settings)
    factory = get_session_factory()
    async with factory() as fresh:
        await assert_safe_test_session(fresh)
        again = (await fresh.execute(select(User).where(User.email == email.lower()))).scalar_one()
        assert str(again.id) == user_id
        login = await AuthService.from_settings(settings).login(
            fresh, email=email, password=STRONG_PASSWORD
        )
        assert str(login.response.user.id) == user_id


@pytest.mark.asyncio
async def test_register_normalizes_email_and_rejects_duplicate(
    auth_client: AsyncClient,
) -> None:
    email = _email("Norm-Case")
    body = {
        "email": email,
        "password": STRONG_PASSWORD,
        "confirm_password": STRONG_PASSWORD,
        "full_name": "Norm",
    }
    first = await auth_client.post("/api/v1/auth/register", json=body)
    assert first.status_code == 201
    assert first.json()["user"]["email"] == email.lower()
    second = await auth_client.post(
        "/api/v1/auth/register",
        json={**body, "email": email.upper()},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "email_already_registered"


@pytest.mark.asyncio
async def test_login_refresh_logout_lifecycle(
    auth_client: AsyncClient,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    email = _email("lifecycle")
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
            "full_name": "Lifecycle",
        },
    )
    assert registered.status_code == 201
    auth_client.cookies.clear()

    wrong = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!!!x"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "invalid_credentials"

    unknown = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody-xyz@example.com", "password": STRONG_PASSWORD},
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "invalid_credentials"

    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email.upper(), "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200
    assert settings.auth_cookie_name in login.cookies
    token = login.json()["access_token"]

    me = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == email.lower()

    refresh = await auth_client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["access_token"]

    logout = await auth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    after_logout = await auth_client.post("/api/v1/auth/refresh")
    assert after_logout.status_code == 401

    auth_client.cookies.clear()
    again = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": STRONG_PASSWORD},
    )
    assert again.status_code == 200

    # Prove we are still on the isolated test DB (never cortexa_agent).
    db_name = (await db_session.execute(text("SELECT current_database()"))).scalar_one()
    assert db_name == "cortexa_agent_test"
    identity = (
        await db_session.execute(
            text("SELECT value FROM application_metadata WHERE key='database_identity'")
        )
    ).scalar_one()
    assert identity == "cortexa-agent-test"


@pytest.mark.asyncio
async def test_recreate_auth_service_still_logs_in(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    email = _email("recreate-svc")
    auth_a = AuthService.from_settings(settings)
    registered = await auth_a.register(
        db_session,
        email=email,
        password=STRONG_PASSWORD,
        full_name="Recreate",
    )
    user_id = registered.response.user.id

    auth_b = AuthService.from_settings(settings)
    login = await auth_b.login(db_session, email=email, password=STRONG_PASSWORD)
    assert login.response.user.id == user_id
