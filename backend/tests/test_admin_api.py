"""Phase 8 admin authorization and foundation API tests."""

from __future__ import annotations

import uuid

import pytest
from app.models.enums import UserRole
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
