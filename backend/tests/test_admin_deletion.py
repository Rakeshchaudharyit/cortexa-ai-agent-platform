"""Phase 8.1 administrator login and session-event tests."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.admin import PlatformSetting, ToolConfiguration
from app.models.document import Document, DocumentChunk
from app.models.enums import (
    DocumentStatus,
    MemoryCategory,
    MemorySource,
    MemoryStatus,
    ToolExecutionStatus,
    UserRole,
    UserStatus,
)
from app.models.memory import UserMemory
from app.models.refresh_session import RefreshSession
from app.models.tool_execution import ToolExecution
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy import func, select
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


async def _two_admins(client: AsyncClient, session: AsyncSession) -> tuple[dict, dict]:
    a = await _register(client, f"adm-a-{uuid.uuid4().hex[:8]}@example.com", name="Admin A")
    b = await _register(client, f"adm-b-{uuid.uuid4().hex[:8]}@example.com", name="Admin B")
    await _promote_admin(session, uuid.UUID(a["user"]["id"]))
    await _promote_admin(session, uuid.UUID(b["user"]["id"]))
    return a, b


# ── Login / session events ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_login_and_ack(chat_client: AsyncClient, db_session: AsyncSession) -> None:
    email = f"admlogin-{uuid.uuid4().hex[:8]}@example.com"
    payload = await _register(chat_client, email, name="Admin Login")
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))

    login = await chat_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongDemoPassword123!"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"
    token = login.json()["access_token"]

    ack = await chat_client.post(
        "/api/v1/admin/session/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ack.status_code == 204

    audit = await chat_client.get(
        "/api/v1/admin/audit?action=admin_login_success",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert audit.status_code == 200
    assert audit.json()["total"] >= 1


@pytest.mark.asyncio
async def test_normal_user_denied_login_event(chat_client: AsyncClient) -> None:
    payload = await _register(chat_client, f"normlogin-{uuid.uuid4().hex[:8]}@example.com")
    denied = await chat_client.post(
        "/api/v1/admin/session/denied",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert denied.status_code == 204


@pytest.mark.asyncio
async def test_invalid_credentials_enumeration_safe(chat_client: AsyncClient) -> None:
    resp = await chat_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "WrongPassword999!"},
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_disabled_admin_cannot_login(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    email = f"dislogin-{uuid.uuid4().hex[:8]}@example.com"
    payload = await _register(chat_client, email)
    user = await db_session.get(User, uuid.UUID(payload["user"]["id"]))
    assert user is not None
    user.role = UserRole.admin
    user.status = UserStatus.disabled
    await db_session.commit()
    resp = await chat_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongDemoPassword123!"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_logout_invalidates_refresh(
    chat_client: AsyncClient, db_session: AsyncSession, settings
) -> None:
    email = f"admlogout-{uuid.uuid4().hex[:8]}@example.com"
    payload = await _register(chat_client, email)
    await _promote_admin(db_session, uuid.UUID(payload["user"]["id"]))
    login = await chat_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongDemoPassword123!"},
    )
    assert login.status_code == 200
    refresh_cookie = login.cookies.get(settings.auth_cookie_name)
    assert refresh_cookie
    logout = await chat_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert logout.status_code in {200, 204}
    refreshed = await chat_client.post("/api/v1/auth/refresh")
    assert refreshed.status_code in {401, 403}
