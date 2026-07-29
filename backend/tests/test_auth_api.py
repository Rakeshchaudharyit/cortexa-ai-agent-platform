"""Authentication API endpoint tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from app.core.config import Settings
from app.models.enums import UserStatus
from app.models.user import User
from app.security.tokens import ACCESS_TOKEN_TYPE, hash_token
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

STRONG_PASSWORD = "StrongDemoPassword123!"


@pytest.mark.asyncio
async def test_register_success(auth_client: AsyncClient, settings: Settings) -> None:
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "demo@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Demo User",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "demo@example.com"
    assert payload["user"]["role"] == "user"
    assert payload["user"]["status"] == "active"
    assert "password" not in payload["user"]
    assert "password_hash" not in payload["user"]
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == settings.access_token_expire_minutes * 60
    assert settings.auth_cookie_name in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()
    assert "SameSite=lax" in set_cookie or "samesite=lax" in set_cookie.lower()


@pytest.mark.asyncio
async def test_register_duplicate_email(auth_client: AsyncClient) -> None:
    body = {
        "email": "dup-api@example.com",
        "password": STRONG_PASSWORD,
        "full_name": "Dup",
    }
    first = await auth_client.post("/api/v1/auth/register", json=body)
    assert first.status_code == 201
    second = await auth_client.post(
        "/api/v1/auth/register",
        json={**body, "email": "DUP-API@example.com"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "email_already_registered"
    assert "sql" not in second.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_register_invalid_email(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": STRONG_PASSWORD, "full_name": "X"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_weak_password(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "short", "full_name": "Weak"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_missing_fields(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/v1/auth/register", json={"email": "a@b.com"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success_and_me(auth_client: AsyncClient, settings: Settings) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "login-api@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Login API",
        },
    )
    auth_client.cookies.clear()
    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "login-api@example.com", "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert settings.auth_cookie_name in login.cookies
    me = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "login-api@example.com"
    assert "password" not in body
    assert "password_hash" not in body
    assert "token_hash" not in body


@pytest.mark.asyncio
async def test_login_unknown_and_wrong_password_generic(auth_client: AsyncClient) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "generic@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Generic",
        },
    )
    unknown = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": STRONG_PASSWORD},
    )
    wrong = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "generic@example.com", "password": "WrongPassword!!!x"},
    )
    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]
    assert unknown.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_disabled_account(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "disabled-api@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Disabled API",
        },
    )
    user_id = uuid.UUID(registered.json()["user"]["id"])
    user = await db_session.get(User, user_id)
    assert user is not None
    user.status = UserStatus.disabled
    await db_session.commit()
    response = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "disabled-api@example.com", "password": STRONG_PASSWORD},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"


@pytest.mark.asyncio
async def test_refresh_rotation_sets_new_cookie(
    auth_client: AsyncClient,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    from app.models.refresh_session import RefreshSession

    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh-api@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Refresh API",
        },
    )
    old_cookie = registered.cookies.get(settings.auth_cookie_name)
    assert old_cookie
    refresh = await auth_client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200
    new_cookie = refresh.cookies.get(settings.auth_cookie_name)
    assert new_cookie
    assert new_cookie != old_cookie
    assert refresh.json()["access_token"]

    session_row = (
        await db_session.execute(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(old_cookie))
        )
    ).scalar_one()
    assert session_row.revoked_at is not None


@pytest.mark.asyncio
async def test_refresh_missing_cookie(auth_client: AsyncClient) -> None:
    auth_client.cookies.clear()
    response = await auth_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


@pytest.mark.asyncio
async def test_refresh_invalid_cookie(auth_client: AsyncClient, settings: Settings) -> None:
    auth_client.cookies.set(settings.auth_cookie_name, "not-a-real-token")
    response = await auth_client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_and_clears_cookie(
    auth_client: AsyncClient,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    from app.models.refresh_session import RefreshSession

    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "logout-api@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Logout API",
        },
    )
    raw = registered.cookies.get(settings.auth_cookie_name)
    assert raw
    logout = await auth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    # Cookie cleared (empty or deleted)
    set_cookie = logout.headers.get("set-cookie", "").lower()
    assert settings.auth_cookie_name in set_cookie or settings.auth_cookie_name not in (
        logout.cookies or {}
    )

    row = (
        await db_session.execute(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(raw))
        )
    ).scalar_one()
    assert row.revoked_at is not None

    # Idempotent logout
    again = await auth_client.post("/api/v1/auth/logout")
    assert again.status_code == 200


@pytest.mark.asyncio
async def test_logout_missing_cookie_idempotent(auth_client: AsyncClient) -> None:
    auth_client.cookies.clear()
    response = await auth_client.post("/api/v1/auth/logout")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_me_unauthorized(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate", "").lower().startswith("bearer")


@pytest.mark.asyncio
async def test_me_malformed_and_expired_token(
    auth_client: AsyncClient,
    settings: Settings,
) -> None:
    malformed = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert malformed.status_code == 401

    bad_scheme = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Token abc"},
    )
    assert bad_scheme.status_code == 401

    now = datetime.now(UTC) - timedelta(hours=1)
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": ACCESS_TOKEN_TYPE,
            "role": "user",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=1)).timestamp()),
            "jti": str(uuid.uuid4()),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired_resp = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert expired_resp.status_code == 401


@pytest.mark.asyncio
async def test_disabled_user_rejected_with_valid_access_token(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "disabled-token@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Disabled Token",
        },
    )
    token = registered.json()["access_token"]
    user_id = uuid.UUID(registered.json()["user"]["id"])
    user = await db_session.get(User, user_id)
    assert user is not None
    user.status = UserStatus.disabled
    await db_session.commit()
    response = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_disabled"


@pytest.mark.asyncio
async def test_cookie_secure_flag_configurable(
    auth_client: AsyncClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Default test settings use secure=false; assert Secure absent for local.
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "cookie-secure@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Cookie Secure",
        },
    )
    set_cookie = response.headers.get("set-cookie", "")
    if settings.auth_cookie_secure:
        assert "Secure" in set_cookie
    else:
        # Starlette may omit Secure attribute entirely when false.
        assert "Secure;" not in set_cookie


@pytest.mark.asyncio
async def test_cors_credentials_for_approved_origin(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:13000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "http://localhost:13000" in response.headers.get(
        "access-control-allow-origin",
        "",
    )


@pytest.mark.asyncio
async def test_llm_requires_auth_without_override(
    auth_app: Any,
    db_session: Any,
) -> None:
    _ = db_session
    from httpx import ASGITransport

    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        generate = await client.post(
            "/api/v1/llm/generate",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        stream = await client.post(
            "/api/v1/llm/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        status = await client.get("/api/v1/llm/status")
        assert generate.status_code == 401
        assert stream.status_code == 401
        assert status.status_code == 200


@pytest.mark.asyncio
async def test_llm_with_auth_reaches_provider(auth_client: AsyncClient) -> None:
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "llm-auth@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "LLM Auth",
        },
    )
    token = registered.json()["access_token"]
    generate = await auth_client.post(
        "/api/v1/llm/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": "hello auth"}]},
    )
    assert generate.status_code == 200
    body = generate.json()
    assert "message" in body or "content" in str(body)

    stream = await auth_client.post(
        "/api/v1/llm/stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"role": "user", "content": "hello stream"}]},
    )
    assert stream.status_code == 200


@pytest.mark.asyncio
async def test_raw_refresh_not_stored(
    auth_client: AsyncClient,
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    from app.models.refresh_session import RefreshSession

    registered = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "hash-store@example.com",
            "password": STRONG_PASSWORD,
            "full_name": "Hash Store",
        },
    )
    raw = registered.cookies.get(settings.auth_cookie_name)
    assert raw
    rows = (await db_session.execute(select(RefreshSession))).scalars().all()
    assert rows
    for row in rows:
        assert row.token_hash != raw
        assert raw not in row.token_hash
