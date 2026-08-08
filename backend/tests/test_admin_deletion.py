"""Phase 8.1 admin deletion, deactivation, and login-event tests."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.admin import PlatformSetting, ToolConfiguration
from app.models.document import Document, DocumentChunk, KnowledgeDocument
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


# ── User deletion ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_deletion_impact_and_authz(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    target = await _register(chat_client, f"tgt-imp-{uuid.uuid4().hex[:8]}@example.com")
    headers = {"Authorization": f"Bearer {admin['access_token']}"}

    ok = await chat_client.get(
        f"/api/v1/admin/users/{target['user']['id']}/deletion-impact",
        headers=headers,
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["can_delete"] is True
    assert "password" not in str(body).lower()

    normal = await _register(chat_client, f"norm-imp-{uuid.uuid4().hex[:8]}@example.com")
    forbidden = await chat_client.get(
        f"/api/v1/admin/users/{target['user']['id']}/deletion-impact",
        headers={"Authorization": f"Bearer {normal['access_token']}"},
    )
    assert forbidden.status_code == 403

    anon = await chat_client.get(
        f"/api/v1/admin/users/{target['user']['id']}/deletion-impact",
    )
    assert anon.status_code == 401


@pytest.mark.asyncio
async def test_cannot_delete_self(chat_client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    resp = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/users/{admin['user']['id']}",
        headers={"Authorization": f"Bearer {admin['access_token']}"},
        json={"confirmation_email": admin["user"]["email"]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "self_deletion_forbidden"


@pytest.mark.asyncio
async def test_cannot_delete_final_active_admin_via_demote_path(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Last-admin safeguard: sole active admin cannot be demoted/disabled."""
    admin = await _register(chat_client, f"sole-{uuid.uuid4().hex[:8]}@example.com")
    await _promote_admin(db_session, uuid.UUID(admin["user"]["id"]))
    # Disable every other active admin created earlier in the DB if any
    others = (
        (
            await db_session.execute(
                select(User).where(
                    User.role == UserRole.admin,
                    User.status == UserStatus.active,
                    User.id != uuid.UUID(admin["user"]["id"]),
                )
            )
        )
        .scalars()
        .all()
    )
    for other in others:
        other.status = UserStatus.disabled
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    # Self-delete blocked first
    delete = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/users/{admin['user']['id']}",
        headers=headers,
        json={"confirmation_email": admin["user"]["email"]},
    )
    assert delete.status_code == 409

    disable = await chat_client.post(
        f"/api/v1/admin/users/{admin['user']['id']}/deactivate",
        headers=headers,
    )
    assert disable.status_code == 409
    assert disable.json()["error"]["code"] == "last_admin_protected"


@pytest.mark.asyncio
async def test_deactivate_activate_revokes_sessions(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    target = await _register(chat_client, f"deact-{uuid.uuid4().hex[:8]}@example.com")
    target_id = uuid.UUID(target["user"]["id"])

    session_row = RefreshSession(
        id=uuid.uuid4(),
        user_id=target_id,
        token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        family_id=uuid.uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(session_row)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    deact = await chat_client.post(
        f"/api/v1/admin/users/{target_id}/deactivate",
        headers=headers,
    )
    assert deact.status_code == 200, deact.text
    assert deact.json()["sessions_revoked"] >= 1
    await db_session.refresh(session_row)
    assert session_row.revoked_at is not None

    act = await chat_client.post(
        f"/api/v1/admin/users/{target_id}/activate",
        headers=headers,
    )
    assert act.status_code == 200
    assert act.json()["user"]["status"] == "active"


@pytest.mark.asyncio
async def test_permanent_user_deletion_cleanup(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    target = await _register(chat_client, f"purge-{uuid.uuid4().hex[:8]}@example.com")
    target_id = uuid.UUID(target["user"]["id"])
    email = target["user"]["email"]

    knowledge = KnowledgeDocument(
        id=uuid.uuid4(), user_id=target_id, title="notes.txt", tags=[]
    )
    db_session.add(knowledge)
    await db_session.flush()
    doc = Document(
        id=uuid.uuid4(),
        user_id=target_id,
        knowledge_document_id=knowledge.id,
        filename="notes.txt",
        original_filename="notes.txt",
        media_type="text/plain",
        file_size_bytes=12,
        checksum_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        storage_key=f"{target_id}/{uuid.uuid4().hex}.txt",
        status=DocumentStatus.ready,
        chunk_count=1,
        character_count=12,
    )
    db_session.add(doc)
    await db_session.flush()
    knowledge.active_version_id = doc.id
    db_session.add(
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            user_id=target_id,
            chunk_index=0,
            content="hello world!",
            content_sha256=hashlib.sha256(b"hello world!").hexdigest(),
            character_count=12,
            embedding=[0.01] * 768,
            chunk_metadata={},
        )
    )
    db_session.add(
        UserMemory(
            id=uuid.uuid4(),
            user_id=target_id,
            title="Pref",
            content="likes tea",
            normalized_content="likes tea",
            category=MemoryCategory.preference,
            source=MemorySource.explicit_user_request,
            status=MemoryStatus.active,
        )
    )
    db_session.add(
        ToolExecution(
            id=uuid.uuid4(),
            user_id=target_id,
            tool_name="calculator",
            tool_version="1.0.0",
            status=ToolExecutionStatus.succeeded,
            arguments_json={"expression": "1+1"},
            result_json={"value": 2},
        )
    )
    db_session.add(
        RefreshSession(
            id=uuid.uuid4(),
            user_id=target_id,
            token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            family_id=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(days=3),
        )
    )
    await db_session.commit()
    tool_id = await db_session.scalar(
        select(ToolExecution.id).where(ToolExecution.user_id == target_id)
    )

    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    impact = await chat_client.get(
        f"/api/v1/admin/users/{target_id}/deletion-impact",
        headers=headers,
    )
    assert impact.status_code == 200
    assert impact.json()["documents"] >= 1
    assert impact.json()["tool_executions"] >= 1

    deleted = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/users/{target_id}",
        headers=headers,
        json={"confirmation_email": email},
    )
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["tool_executions_anonymized"] >= 1
    assert "password" not in str(body).lower()
    assert "/" not in body.get("email_fingerprint", "")  # no paths

    assert await db_session.get(User, target_id) is None
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Document).where(Document.user_id == target_id)
        )
        or 0
    ) == 0
    te = await db_session.get(ToolExecution, tool_id)
    assert te is not None
    assert te.user_id is None
    assert te.arguments_json.get("redacted") is True

    audit = await chat_client.get(
        "/api/v1/admin/audit?action=user_permanently_deleted",
        headers=headers,
    )
    assert audit.status_code == 200
    assert audit.json()["total"] >= 1
    audit_blob = str(audit.json()).lower()
    assert "likes tea" not in audit_blob
    assert "strongdemopassword" not in audit_blob

    # Target can no longer log in
    login = await chat_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongDemoPassword123!"},
    )
    assert login.status_code == 401


# ── Documents / conversations / memories ───────────────────────────────────


@pytest.mark.asyncio
async def test_document_delete_and_impact(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    owner = await _register(chat_client, f"docowner-{uuid.uuid4().hex[:8]}@example.com")
    owner_id = uuid.UUID(owner["user"]["id"])
    knowledge = KnowledgeDocument(
        id=uuid.uuid4(), user_id=owner_id, title="report.pdf", tags=[]
    )
    db_session.add(knowledge)
    await db_session.flush()
    doc = Document(
        id=uuid.uuid4(),
        user_id=owner_id,
        knowledge_document_id=knowledge.id,
        filename="report.pdf",
        original_filename="report.pdf",
        media_type="application/pdf",
        file_size_bytes=100,
        checksum_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        storage_key=f"{owner_id}/{uuid.uuid4().hex}.pdf",
        status=DocumentStatus.ready,
        chunk_count=1,
        character_count=20,
    )
    db_session.add(doc)
    await db_session.flush()
    knowledge.active_version_id = doc.id
    db_session.add(
        DocumentChunk(
            id=uuid.uuid4(),
            document_id=doc.id,
            user_id=owner_id,
            chunk_index=0,
            content="chunk",
            content_sha256=hashlib.sha256(b"chunk").hexdigest(),
            character_count=5,
            embedding=[0.02] * 768,
            chunk_metadata={},
        )
    )
    await db_session.commit()
    document_id = doc.id

    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    impact = await chat_client.get(
        f"/api/v1/admin/documents/{document_id}/deletion-impact",
        headers=headers,
    )
    assert impact.status_code == 200
    assert impact.json()["filename"] == "report.pdf"
    assert "storage_key" not in impact.json() or impact.json().get("storage_key") is None

    missing = await chat_client.get(
        f"/api/v1/admin/documents/{uuid.uuid4()}/deletion-impact",
        headers=headers,
    )
    assert missing.status_code == 404

    deleted = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/documents/{document_id}",
        headers=headers,
        json={"confirmation_filename": "report.pdf"},
    )
    assert deleted.status_code == 204
    db_session.expire_all()
    assert await db_session.get(Document, document_id) is None
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        or 0
    ) == 0

    audit = await chat_client.get(
        "/api/v1/admin/audit?action=document_deleted",
        headers=headers,
    )
    assert audit.json()["total"] >= 1


@pytest.mark.asyncio
async def test_conversation_archive_and_delete(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    owner = await _register(chat_client, f"convowner-{uuid.uuid4().hex[:8]}@example.com")
    headers_owner = {"Authorization": f"Bearer {owner['access_token']}"}
    created = await chat_client.post("/api/v1/conversations", headers=headers_owner, json={})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    impact = await chat_client.get(
        f"/api/v1/admin/conversations/{conversation_id}/deletion-impact",
        headers=headers,
    )
    assert impact.status_code == 200

    archived = await chat_client.post(
        f"/api/v1/admin/conversations/{conversation_id}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    deleted = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/conversations/{conversation_id}",
        headers=headers,
        json={"confirm": True},
    )
    assert deleted.status_code == 204

    audit = await chat_client.get(
        "/api/v1/admin/audit?action=conversation_permanently_deleted",
        headers=headers,
    )
    assert audit.json()["total"] >= 1


@pytest.mark.asyncio
async def test_memory_archive_and_redact(
    chat_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    owner = await _register(chat_client, f"memowner-{uuid.uuid4().hex[:8]}@example.com")
    owner_id = uuid.UUID(owner["user"]["id"])
    mem = UserMemory(
        id=uuid.uuid4(),
        user_id=owner_id,
        title="Secret",
        content="private content never in audit",
        normalized_content="private content never in audit",
        category=MemoryCategory.preference,
        source=MemorySource.explicit_user_request,
        status=MemoryStatus.active,
        embedding=[0.03] * 768,
    )
    db_session.add(mem)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    archived = await chat_client.post(
        f"/api/v1/admin/memories/{mem.id}/archive",
        headers=headers,
    )
    assert archived.status_code == 200

    impact = await chat_client.get(
        f"/api/v1/admin/memories/{mem.id}/deletion-impact",
        headers=headers,
    )
    assert impact.status_code == 200

    deleted = await chat_client.delete(
        f"/api/v1/admin/memories/{mem.id}",
        headers=headers,
    )
    assert deleted.status_code == 204
    await db_session.refresh(mem)
    assert mem.status == MemoryStatus.deleted
    assert mem.embedding is None
    assert "private content" not in (mem.content or "")

    audit = await chat_client.get(
        "/api/v1/admin/audit?action=memory_deleted",
        headers=headers,
    )
    assert audit.json()["total"] >= 1
    assert "private content never in audit" not in str(audit.json())


# ── Configuration resets ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_and_setting_reset(chat_client: AsyncClient, db_session: AsyncSession) -> None:
    admin, _ = await _two_admins(chat_client, db_session)
    headers = {"Authorization": f"Bearer {admin['access_token']}"}
    admin_id = uuid.UUID(admin["user"]["id"])

    # Create tool override
    patch = await chat_client.patch(
        "/api/v1/admin/tools/calculator",
        headers=headers,
        json={"enabled": False},
    )
    assert patch.status_code == 200, patch.text

    reset = await chat_client.delete(
        "/api/v1/admin/tools/calculator/configuration",
        headers=headers,
    )
    assert reset.status_code == 200
    assert reset.json()["tool"]["enabled"] is True

    unknown = await chat_client.delete(
        "/api/v1/admin/tools/not_a_real_tool/configuration",
        headers=headers,
    )
    assert unknown.status_code == 404

    # Setting override + reset
    updated = await chat_client.patch(
        "/api/v1/admin/settings",
        headers=headers,
        json={"updates": {"platform_display_name": "Temp Admin Name"}},
    )
    assert updated.status_code == 200

    reset_setting = await chat_client.delete(
        "/api/v1/admin/settings/platform_display_name",
        headers=headers,
    )
    assert reset_setting.status_code == 200
    settings = await chat_client.get("/api/v1/admin/settings", headers=headers)
    item = next(s for s in settings.json()["settings"] if s["key"] == "platform_display_name")
    assert item["source"] == "default"

    unsafe = await chat_client.delete(
        "/api/v1/admin/settings/jwt_secret_key",
        headers=headers,
    )
    assert unsafe.status_code == 422

    # No audit deletion endpoint
    audit_delete = await chat_client.delete("/api/v1/admin/audit", headers=headers)
    assert audit_delete.status_code in {404, 405}

    # Ensure configs cleaned
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ToolConfiguration)
            .where(ToolConfiguration.tool_name == "calculator")
        )
        or 0
    ) == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(PlatformSetting)
            .where(PlatformSetting.key == "platform_display_name")
        )
        or 0
    ) == 0
    _ = admin_id


@pytest.mark.asyncio
async def test_destructive_endpoints_authz(chat_client: AsyncClient) -> None:
    uid = uuid.uuid4()
    anon = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/users/{uid}",
        json={"confirmation_email": "x@example.com"},
    )
    assert anon.status_code == 401

    user = await _register(chat_client, f"authz-{uuid.uuid4().hex[:8]}@example.com")
    forbidden = await chat_client.request(
        "DELETE",
        f"/api/v1/admin/users/{uid}",
        headers={"Authorization": f"Bearer {user['access_token']}"},
        json={"confirmation_email": "x@example.com"},
    )
    assert forbidden.status_code == 403
