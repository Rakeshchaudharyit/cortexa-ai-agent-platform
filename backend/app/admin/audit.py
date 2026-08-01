"""Administrative audit event recording."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.policies import sanitize_audit_metadata
from app.models.admin import AdminAuditEvent
from app.security.tokens import hash_optional_metadata


class AdminAuditService:
    """Append-only admin audit writer."""

    async def record(
        self,
        session: AsyncSession,
        *,
        actor_user_id: uuid.UUID | None,
        action: str,
        target_type: str,
        safe_summary: str,
        target_id: str | None = None,
        target_user_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        commit: bool = False,
    ) -> AdminAuditEvent:
        event = AdminAuditEvent(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            action=action.strip()[:64],
            target_type=target_type.strip()[:64],
            target_id=(target_id[:128] if target_id else None),
            target_user_id=target_user_id,
            safe_summary=safe_summary.strip()[:500],
            metadata_json=sanitize_audit_metadata(metadata),
            request_id=(request_id[:128] if request_id else None),
            ip_hash=hash_optional_metadata(ip_address),
            user_agent_hash=hash_optional_metadata(user_agent),
        )
        session.add(event)
        await session.flush()
        if commit:
            await session.commit()
        return event


# Module-level convenience used by routes/services.
_audit_service = AdminAuditService()


async def record_admin_action(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str,
    safe_summary: str,
    target_id: str | None = None,
    target_user_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    commit: bool = False,
) -> AdminAuditEvent:
    return await _audit_service.record(
        session,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        safe_summary=safe_summary,
        target_id=target_id,
        target_user_id=target_user_id,
        metadata=metadata,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        commit=commit,
    )
