"""Phase 8 admin authorization and foundation API tests."""

from __future__ import annotations

import uuid

import pytest
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _register(client: AsyncClient, email: str, *, name: str = "User") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongDemoPassword123!",
            "confirm_password": "StrongDemoPassword123!",
            "full_name": name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _promote_admin(session: AsyncSession, user_id: uuid.UUID) -> None:
    user = await session.get(User, user_id)
    assert user is not None
    user.role = UserRole.admin
    await session.commit()


@pytest.mark.asyncio
async def test_admin_dashboard_anonymous_401(chat_client: AsyncClient) -> None:
    response = await chat_client.get("/api/v1/admin/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_dashboard_normal_user_403(chat_client: AsyncClient) -> None:
    token = (await _register(chat_client, f"user-{uuid.uuid4().hex[:8]}@example.com"))[
        "access_token"
    ]
    response = await chat_client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_admin_dashboard_admin_ok(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"admin-{uuid.uuid4().hex[:8]}@example.com")
    user_id = uuid.UUID(payload["user"]["id"])
    await _promote_admin(db_session, user_id)
    # Re-login so access token role claim is fresh (optional; deps load user from DB).
    token = payload["access_token"]
    response = await chat_client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "metrics" in body
    assert "usage_trend" in body
    assert "password" not in str(body).lower()
    assert "jwt" not in str(body).lower()


@pytest.mark.asyncio
async def test_disabled_admin_denied(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"disadmin-{uuid.uuid4().hex[:8]}@example.com")
    user_id = uuid.UUID(payload["user"]["id"])
    user = await db_session.get(User, user_id)
    assert user is not None
    user.role = UserRole.admin
    user.status = UserStatus.disabled
    await db_session.commit()
    response = await chat_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_admin_users_list_and_no_password_hash(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"admin2-{uuid.uuid4().hex[:8]}@example.com")
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))
    response = await chat_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    blob = str(body).lower()
    assert "password_hash" not in blob
    assert "password" not in blob


@pytest.mark.asyncio
async def test_admin_settings_rejects_unsafe_key(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"admin3-{uuid.uuid4().hex[:8]}@example.com")
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))
    response = await chat_client.patch(
        "/api/v1/admin/settings",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
        json={"updates": {"jwt_secret_key": "should-not-work-at-all-please"}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_settings_update_and_audit(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"admin4-{uuid.uuid4().hex[:8]}@example.com")
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    response = await chat_client.patch(
        "/api/v1/admin/settings",
        headers=headers,
        json={"updates": {"platform_display_name": "Cortexa Admin Demo"}},
    )
    assert response.status_code == 200, response.text
    assert "Cortexa Admin Demo" in str(response.json())
    audit = await chat_client.get("/api/v1/admin/audit?action=settings_updated", headers=headers)
    assert audit.status_code == 200
    assert audit.json()["total"] >= 1


@pytest.mark.asyncio
async def test_admin_cannot_remove_last_admin(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"lastadmin-{uuid.uuid4().hex[:8]}@example.com")
    user_id = uuid.UUID(payload["user"]["id"])
    await _promote_admin(db_session, user_id)
    response = await chat_client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
        json={"role": "user"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin_protected"


@pytest.mark.asyncio
async def test_normal_user_cannot_access_audit(chat_client: AsyncClient) -> None:
    token = (await _register(chat_client, f"noaudit-{uuid.uuid4().hex[:8]}@example.com"))[
        "access_token"
    ]
    response = await chat_client.get(
        "/api/v1/admin/audit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_tools_disable_unknown_rejected(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"admintool-{uuid.uuid4().hex[:8]}@example.com")
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))
    response = await chat_client.patch(
        "/api/v1/admin/tools/not_a_real_tool",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
        json={"enabled": False},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_analytics_accepts_bounded_day_ranges(
    chat_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = await _register(chat_client, f"analytics-{uuid.uuid4().hex[:8]}@example.com")
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))
    headers = {"Authorization": f"Bearer {payload['access_token']}"}
    for days in (7, 30, 90):
        response = await chat_client.get(
            f"/api/v1/admin/analytics?days={days}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["range_days"] == days
        assert isinstance(body["points"], list)
    bad = await chat_client.get("/api/v1/admin/analytics?days=14", headers=headers)
    assert bad.status_code == 422
