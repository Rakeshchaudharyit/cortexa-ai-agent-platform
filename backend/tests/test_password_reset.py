"""Password reset API and service tests (no real email delivery)."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from app.core.config import Settings
from app.models.enums import UserStatus
from app.models.password_reset import PasswordResetToken
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.notifications.providers.development import DevelopmentPasswordResetDelivery
from app.schemas.auth import normalize_email
from app.security.tokens import hash_token
from app.services.auth import AuthService
from app.services.password_reset import (
    FORGOT_PASSWORD_MESSAGE,
    PasswordResetService,
)
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes.redis import FakeRedis

STRONG_PASSWORD = "StrongDemoPassword123!"
NEW_PASSWORD = "BrandNewSecurePass456!"


def _register_body(email: str, password: str = STRONG_PASSWORD) -> dict[str, str]:
    return {
        "email": email,
        "password": password,
        "confirm_password": password,
        "full_name": "Reset User",
    }


def _token_from_url(url: str) -> str:
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("token", [])
    assert values, f"token missing from reset URL: {url}"
    return values[0]


@pytest.mark.asyncio
async def test_register_logout_login_same_password(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Focused diagnostic: register(password X) → logout → login(password X)."""
    email = "lifecycle@example.com"
    password = "ExactSamePassword1!"
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body(email, password),
    )
    assert registered.status_code == 201
    user_id = registered.json()["user"]["id"]

    logout = await auth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    auth_client.cookies.clear()

    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == user_id

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    assert user.password_hash.startswith("$argon2")
    assert len(user.password_hash) >= 80


@pytest.mark.asyncio
async def test_password_whitespace_not_silently_changed(
    auth_client: AsyncClient,
) -> None:
    password = " spaced pass OK!"
    email = "whitespace@example.com"
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body(email, password),
    )
    assert registered.status_code == 201
    auth_client.cookies.clear()

    wrong = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password.strip()},
    )
    assert wrong.status_code == 401

    ok = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_email_normalization_consistent_login(auth_client: AsyncClient) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("  Norm.Case@Example.COM  "),
    )
    auth_client.cookies.clear()
    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "norm.case@example.com", "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_stale_refresh_cookie_does_not_block_login(
    auth_client: AsyncClient,
    settings: Settings,
) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("stale-cookie@example.com"),
    )
    auth_client.cookies.set(settings.auth_cookie_name, "definitely-not-a-valid-refresh")
    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "stale-cookie@example.com", "password": STRONG_PASSWORD},
    )
    assert login.status_code == 200
    assert settings.auth_cookie_name in login.cookies
    assert login.cookies[settings.auth_cookie_name] != "definitely-not-a-valid-refresh"


@pytest.mark.asyncio
async def test_forgot_password_enumeration_safe(
    auth_client: AsyncClient,
    auth_app: Any,
) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("known-reset@example.com"),
    )
    known = await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "known-reset@example.com"},
    )
    unknown = await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "nobody-reset@example.com"},
    )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()
    assert known.json()["message"] == FORGOT_PASSWORD_MESSAGE
    assert "token" not in known.json()
    assert "reset_url" not in known.json()
    assert "http" not in known.text.lower()
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    assert await delivery.get_latest_reset_url("known-reset@example.com")
    assert await delivery.get_latest_reset_url("nobody-reset@example.com") is None


@pytest.mark.asyncio
async def test_forgot_password_inactive_user_no_leak(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_app: Any,
) -> None:
    registered = await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("inactive-reset@example.com"),
    )
    user_id = registered.json()["user"]["id"]
    user = await db_session.get(User, __import__("uuid").UUID(user_id))
    assert user is not None
    user.status = UserStatus.disabled
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "inactive-reset@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == FORGOT_PASSWORD_MESSAGE
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    assert await delivery.get_latest_reset_url("inactive-reset@example.com") is None


@pytest.mark.asyncio
async def test_forgot_stores_hash_not_raw_token(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_app: Any,
) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("hash-store@example.com"),
    )
    await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "hash-store@example.com"},
    )
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    url = await delivery.get_latest_reset_url("hash-store@example.com")
    assert url
    raw = _token_from_url(url)
    result = await db_session.execute(select(PasswordResetToken))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(raw)
    assert raw not in rows[0].token_hash
    assert rows[0].expires_at > datetime.now(UTC)
    assert rows[0].used_at is None
    assert rows[0].revoked_at is None


@pytest.mark.asyncio
async def test_reset_password_full_lifecycle(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_app: Any,
    settings: Settings,
) -> None:
    email = "full-reset@example.com"
    await auth_client.post("/api/v1/auth/register", json=_register_body(email))
    # Create an extra refresh session via login after register cookie clear.
    auth_client.cookies.clear()
    await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": STRONG_PASSWORD},
    )
    await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    # Second active token then revoke older via limit.
    await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})

    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    url = await delivery.get_latest_reset_url(email)
    assert url
    assert url.startswith(settings.password_reset_frontend_url)
    raw = _token_from_url(url)

    mismatch = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw,
            "new_password": NEW_PASSWORD,
            "confirm_password": "DifferentPassword!!",
        },
    )
    assert mismatch.status_code == 422

    weak = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw, "new_password": "short", "confirm_password": "short"},
    )
    assert weak.status_code == 422

    ok = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert ok.status_code == 200
    assert "Password reset successfully" in ok.json()["message"]
    assert "password" not in ok.text.lower() or "Password reset" in ok.json()["message"]

    reuse = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert reuse.status_code == 400

    old_login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": STRONG_PASSWORD},
    )
    assert old_login.status_code == 401

    new_login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200

    user_id = new_login.json()["user"]["id"]
    tokens = (
        (
            await db_session.execute(
                select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    assert all(t.used_at is not None or t.revoked_at is not None for t in tokens)

    sessions = (
        (
            await db_session.execute(
                select(RefreshSession).where(
                    RefreshSession.user_id == new_login.json()["user"]["id"],
                    RefreshSession.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    # Login created a fresh session after reset; older ones must be revoked.
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_reset_rejects_expired_malformed_unknown(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_app: Any,
) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("expire-reset@example.com"),
    )
    await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "expire-reset@example.com"},
    )
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    raw = _token_from_url(await delivery.get_latest_reset_url("expire-reset@example.com") or "")

    result = await db_session.execute(select(PasswordResetToken))
    row = result.scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    expired = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert expired.status_code == 400
    assert "invalid or has expired" in expired.json()["error"]["message"]

    malformed = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "!!!",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert malformed.status_code == 400

    unknown = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "a" * 43,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert unknown.status_code == 400


@pytest.mark.asyncio
async def test_active_token_limit_and_normalized_email(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    email = "limit-reset@example.com"
    await auth_client.post("/api/v1/auth/register", json=_register_body(email))
    for _ in range(settings.password_reset_max_active_tokens + 2):
        response = await auth_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "  LIMIT-RESET@EXAMPLE.COM "},
        )
        assert response.status_code == 200

    now = datetime.now(UTC)
    result = await db_session.execute(select(PasswordResetToken))
    rows = list(result.scalars().all())
    active = [
        row
        for row in rows
        if row.used_at is None and row.revoked_at is None and row.expires_at > now
    ]
    assert len(active) <= settings.password_reset_max_active_tokens


@pytest.mark.asyncio
async def test_concurrent_reset_only_succeeds_once(
    auth_client: AsyncClient,
    auth_app: Any,
) -> None:
    email = "concurrent-reset@example.com"
    await auth_client.post("/api/v1/auth/register", json=_register_body(email))
    await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    raw = _token_from_url(await delivery.get_latest_reset_url(email) or "")

    async def _attempt(password: str) -> int:
        response = await auth_client.post(
            "/api/v1/auth/reset-password",
            json={
                "token": raw,
                "new_password": password,
                "confirm_password": password,
            },
        )
        return response.status_code

    results = await asyncio.gather(
        _attempt("ConcurrentPassOne1!"),
        _attempt("ConcurrentPassTwo2!"),
    )
    assert results.count(200) == 1
    assert results.count(400) == 1


@pytest.mark.asyncio
async def test_password_reset_service_layer_register_login(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    auth = AuthService.from_settings(settings)
    password = "ServiceLayerPass123!"
    await auth.register(
        db_session,
        email="svc-lifecycle@example.com",
        password=password,
        full_name="Svc",
    )
    await auth.logout(db_session, raw_refresh_token=None)
    login = await auth.login(
        db_session,
        email="svc-lifecycle@example.com",
        password=password,
    )
    assert login.response.user.email == normalize_email("svc-lifecycle@example.com")


@pytest.mark.asyncio
async def test_admin_cli_password_set_revokes_sessions(
    db_session: AsyncSession,
    settings: Settings,
) -> None:
    auth = AuthService.from_settings(settings)
    delivery = DevelopmentPasswordResetDelivery(settings=settings, redis=FakeRedis())
    reset_service = PasswordResetService.from_settings(
        settings,
        delivery=delivery,
        redis=None,
    )
    registered = await auth.register(
        db_session,
        email="cli-reset@example.com",
        password=STRONG_PASSWORD,
        full_name="CLI",
    )
    await reset_service.forgot_password(db_session, email="cli-reset@example.com")
    await reset_service.admin_set_password(
        db_session,
        email="CLI-RESET@example.com",
        new_password=NEW_PASSWORD,
    )

    sessions = (
        (
            await db_session.execute(
                select(RefreshSession).where(
                    RefreshSession.user_id == registered.response.user.id,
                    RefreshSession.revoked_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert sessions == []

    tokens = (
        (
            await db_session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == registered.response.user.id,
                    PasswordResetToken.revoked_at.is_(None),
                    PasswordResetToken.used_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert tokens == []

    login = await auth.login(
        db_session,
        email="cli-reset@example.com",
        password=NEW_PASSWORD,
    )
    assert login.response.user.id == registered.response.user.id


@pytest.mark.asyncio
async def test_register_password_mismatch(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "mismatch@example.com",
            "password": STRONG_PASSWORD,
            "confirm_password": "DifferentPassword123!",
            "full_name": "Mismatch",
        },
    )
    assert response.status_code == 422


def test_normalize_email_shared() -> None:
    assert normalize_email("  A@B.Com ") == "a@b.com"


def test_reset_token_entropy(settings: Settings) -> None:
    service = PasswordResetService.from_settings(settings)
    token = service.generate_raw_token()
    assert len(token) >= 22
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", token)


@pytest.mark.asyncio
async def test_dev_delivery_shared_across_separate_instances(
    settings: Settings,
) -> None:
    """Backend writer and CLI reader are separate delivery instances sharing Redis."""
    from app.notifications.base import PasswordResetMessage

    shared = FakeRedis()
    writer = DevelopmentPasswordResetDelivery(settings=settings, redis=shared)
    reader = DevelopmentPasswordResetDelivery(settings=settings, redis=shared)
    email = "cross-process@example.com"
    url = "http://localhost:13000/reset-password?token=shared-raw-token-value"
    await writer.send_password_reset(
        PasswordResetMessage(
            email=email,
            reset_url=url,
            expires_at_iso="2099-01-01T00:00:00+00:00",
        )
    )
    key = writer.delivery_key(email)
    assert email.lower() not in key
    assert "cross-process" not in key
    assert "@" not in key
    ttl = await shared.ttl(key)
    assert 0 < ttl <= settings.password_reset_token_expire_minutes * 60

    consumed = await reader.consume_latest_reset_url(email)
    assert consumed == url
    assert await reader.consume_latest_reset_url(email) is None
    assert await writer.get_latest_reset_url(email) is None


@pytest.mark.asyncio
async def test_dev_delivery_expired_not_retrievable(settings: Settings) -> None:
    import time

    from app.notifications.base import PasswordResetMessage

    redis = FakeRedis()
    delivery = DevelopmentPasswordResetDelivery(settings=settings, redis=redis)
    email = "expired-delivery@example.com"
    await delivery.send_password_reset(
        PasswordResetMessage(
            email=email,
            reset_url="http://localhost:13000/reset-password?token=expired-token",
            expires_at_iso="2099-01-01T00:00:00+00:00",
        )
    )
    key = delivery.delivery_key(email)
    entry = redis._store.get(key)
    assert entry is not None
    value, _ = entry
    redis._store[key] = (value, time.monotonic() - 1)
    assert await delivery.consume_latest_reset_url(email) is None


@pytest.mark.asyncio
async def test_dev_delivery_production_retrieval_refused(settings: Settings) -> None:
    from app.notifications.base import PasswordResetMessage

    redis = FakeRedis()
    prod = settings.model_copy(update={"app_env": "production"})
    delivery = DevelopmentPasswordResetDelivery(settings=prod, redis=redis)
    with pytest.raises(RuntimeError, match="disabled in production"):
        await delivery.send_password_reset(
            PasswordResetMessage(
                email="prod@example.com",
                reset_url="http://localhost:13000/reset-password?token=x",
                expires_at_iso="2099-01-01T00:00:00+00:00",
            )
        )
    with pytest.raises(RuntimeError, match="disabled in production"):
        await delivery.consume_latest_reset_url("prod@example.com")


def test_cli_production_refuses(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    from app.cli import get_password_reset_link as cli_mod
    from app.core.config import clear_settings_cache

    _ = settings
    monkeypatch.setenv("APP_ENV", "production")
    clear_settings_cache()
    try:
        code = cli_mod.main(["--email", "anyone@example.com"])
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        clear_settings_cache()
    assert code == 2


@pytest.mark.asyncio
async def test_forgot_redis_unavailable_same_public_response(
    auth_client: AsyncClient,
    auth_app: Any,
) -> None:
    await auth_client.post(
        "/api/v1/auth/register",
        json=_register_body("redis-down@example.com"),
    )
    redis: FakeRedis = auth_app.state.redis
    redis.unavailable = True
    known = await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "redis-down@example.com"},
    )
    unknown = await auth_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing-redis-down@example.com"},
    )
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json() == unknown.json()
    assert known.json()["message"] == FORGOT_PASSWORD_MESSAGE
    assert "token" not in known.json()


@pytest.mark.asyncio
async def test_forgot_logs_omit_raw_token_and_url(
    auth_client: AsyncClient,
    auth_app: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    email = "log-safe@example.com"
    await auth_client.post("/api/v1/auth/register", json=_register_body(email))
    with caplog.at_level(logging.INFO):
        await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    url = await delivery.get_latest_reset_url(email)
    assert url
    raw = _token_from_url(url)
    joined = "\n".join(r.message for r in caplog.records)
    assert raw not in joined
    assert url not in joined
    assert "token=" not in joined


@pytest.mark.asyncio
async def test_forgot_supersedes_previous_delivery(
    auth_client: AsyncClient,
    auth_app: Any,
) -> None:
    email = "supersede@example.com"
    await auth_client.post("/api/v1/auth/register", json=_register_body(email))
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    first = await delivery.get_latest_reset_url(email)
    await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    second = await delivery.get_latest_reset_url(email)
    assert first and second
    assert first != second
    assert await delivery.consume_latest_reset_url(email) == second
    assert await delivery.consume_latest_reset_url(email) is None


@pytest.mark.asyncio
async def test_reset_with_consumed_delivery_token_lifecycle(
    auth_client: AsyncClient,
    auth_app: Any,
) -> None:
    email = "consume-lifecycle@example.com"
    await auth_client.post("/api/v1/auth/register", json=_register_body(email))
    await auth_client.post("/api/v1/auth/forgot-password", json={"email": email})
    delivery: DevelopmentPasswordResetDelivery = auth_app.state.password_reset_delivery
    url = await delivery.consume_latest_reset_url(email)
    assert url
    assert await delivery.consume_latest_reset_url(email) is None
    raw = _token_from_url(url)

    ok = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert ok.status_code == 200

    old_login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": STRONG_PASSWORD},
    )
    assert old_login.status_code == 401

    new_login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200

    reuse = await auth_client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": raw,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
    )
    assert reuse.status_code == 400
