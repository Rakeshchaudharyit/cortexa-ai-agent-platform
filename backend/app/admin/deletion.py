"""Controlled permanent user deletion for enterprise administration."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import record_admin_action
from app.admin.exceptions import (
    AdminNotFoundError,
    AdminValidationError,
    LastAdminProtectionError,
    SelfDeletionError,
)
from app.admin.repository import AdminRepository
from app.models.conversation import Conversation, Message
from app.models.document import Document, DocumentChunk
from app.models.enums import UserRole, UserStatus
from app.models.memory import UserMemory
from app.models.refresh_session import RefreshSession
from app.models.tool_execution import ToolExecution
from app.models.user import User
from app.services.auth import AuthService

logger = logging.getLogger("cortexa.admin.deletion")


def email_fingerprint(email: str) -> str:
    """Stable non-reversible identifier for audit retention after user deletion."""
    normalized = email.strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:32]


@dataclass(slots=True)
class UserDeletionImpact:
    user_id: uuid.UUID
    documents: int
    document_chunks: int
    conversations: int
    messages: int
    memories: int
    refresh_sessions: int
    tool_executions: int
    can_delete: bool
    blocking_reason: str | None


@dataclass(slots=True)
class UserDeletionResult:
    user_id: uuid.UUID
    email_fingerprint: str
    documents_deleted: int
    document_chunks_deleted: int
    conversations_deleted: int
    messages_deleted: int
    memories_deleted: int
    refresh_sessions_revoked: int
    tool_executions_anonymized: int
    storage_cleanup_failures: int


class AdminUserDeletionService:
    """Orchestrates safe permanent user deletion with governance-preserving cleanup."""

    def __init__(
        self,
        *,
        auth_service: AuthService,
        document_service: Any | None = None,
        repository: AdminRepository | None = None,
    ) -> None:
        self.auth_service = auth_service
        self.document_service = document_service
        self.repo = repository or AdminRepository()

    async def get_impact(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
    ) -> UserDeletionImpact:
        user = await self._lock_user(session, user_id)
        counts = await self._count_dependencies(session, user_id)
        can_delete, reason = self._deletion_guards(actor=actor, target=user, active_admins=None)
        if can_delete and user.role == UserRole.admin and user.status == UserStatus.active:
            active_admins = await self.repo.count_active_admins(session)
            can_delete, reason = self._deletion_guards(
                actor=actor, target=user, active_admins=active_admins
            )
        return UserDeletionImpact(
            user_id=user.id,
            documents=counts["documents"],
            document_chunks=counts["document_chunks"],
            conversations=counts["conversations"],
            messages=counts["messages"],
            memories=counts["memories"],
            refresh_sessions=counts["refresh_sessions"],
            tool_executions=counts["tool_executions"],
            can_delete=can_delete,
            blocking_reason=reason,
        )

    async def delete_user(
        self,
        session: AsyncSession,
        *,
        actor: User,
        user_id: uuid.UUID,
        confirmation_email: str,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserDeletionResult:
        user = await self._lock_user(session, user_id)
        if confirmation_email.strip().lower() != user.email.strip().lower():
            raise AdminValidationError("Confirmation email does not match the target account")

        active_admins = await self.repo.count_active_admins(session)
        can_delete, reason = self._deletion_guards(
            actor=actor, target=user, active_admins=active_admins
        )
        if not can_delete:
            if reason and "own account" in reason.lower():
                raise SelfDeletionError()
            raise LastAdminProtectionError(reason or "Deletion blocked")

        counts = await self._count_dependencies(session, user.id)
        storage_keys = await self._list_storage_keys(session, user.id)
        fingerprint = email_fingerprint(user.email)

        # Anonymize governance tool executions before user row removal.
        anonymized = await self._anonymize_tool_executions(session, user.id)

        revoked = await self.auth_service.revoke_all_user_sessions(
            session, user_id=user.id, commit=False
        )

        await record_admin_action(
            session,
            actor_user_id=actor.id,
            action="user_permanently_deleted",
            target_type="user",
            target_id=str(user.id),
            target_user_id=user.id,
            safe_summary=(
                f"Permanently deleted user fingerprint={fingerprint} "
                f"(docs={counts['documents']}, conversations={counts['conversations']})"
            ),
            metadata={
                "email_fingerprint": fingerprint,
                "documents": counts["documents"],
                "document_chunks": counts["document_chunks"],
                "conversations": counts["conversations"],
                "messages": counts["messages"],
                "memories": counts["memories"],
                "refresh_sessions": counts["refresh_sessions"],
                "tool_executions_anonymized": anonymized,
                "role": user.role.value,
                "status": user.status.value,
            },
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await session.delete(user)
        await session.commit()

        storage_failures = await self._cleanup_storage(storage_keys)
        if storage_failures:
            logger.warning(
                "user_deletion_storage_cleanup_partial user_id=%s failures=%s",
                user_id,
                storage_failures,
            )
            # Best-effort follow-up audit (DB already committed user deletion).
            try:
                await record_admin_action(
                    session,
                    actor_user_id=actor.id,
                    action="user_deletion_storage_cleanup_failed",
                    target_type="user",
                    target_id=str(user_id),
                    safe_summary=(
                        f"Storage cleanup incomplete for deleted user "
                        f"fingerprint={fingerprint} (failures={storage_failures})"
                    ),
                    metadata={
                        "email_fingerprint": fingerprint,
                        "storage_cleanup_failures": storage_failures,
                    },
                    request_id=request_id,
                    commit=True,
                )
            except Exception:  # noqa: BLE001
                logger.warning("user_deletion_cleanup_audit_failed user_id=%s", user_id)

        return UserDeletionResult(
            user_id=user_id,
            email_fingerprint=fingerprint,
            documents_deleted=counts["documents"],
            document_chunks_deleted=counts["document_chunks"],
            conversations_deleted=counts["conversations"],
            messages_deleted=counts["messages"],
            memories_deleted=counts["memories"],
            refresh_sessions_revoked=revoked,
            tool_executions_anonymized=anonymized,
            storage_cleanup_failures=storage_failures,
        )

    def _deletion_guards(
        self,
        *,
        actor: User,
        target: User,
        active_admins: int | None,
    ) -> tuple[bool, str | None]:
        if actor.id == target.id:
            return False, "Cannot delete your own account"
        if (
            active_admins is not None
            and target.role == UserRole.admin
            and target.status == UserStatus.active
            and active_admins <= 1
        ):
            return False, "Cannot delete the last active admin account"
        return True, None

    async def _lock_user(self, session: AsyncSession, user_id: uuid.UUID) -> User:
        user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise AdminNotFoundError("User not found")
        return user

    async def _count_dependencies(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> dict[str, int]:
        documents = int(
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.user_id == user_id)
            )
            or 0
        )
        chunks = int(
            await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.user_id == user_id)
            )
            or 0
        )
        conversations = int(
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == user_id)
            )
            or 0
        )
        messages = int(
            await session.scalar(
                select(func.count()).select_from(Message).where(Message.user_id == user_id)
            )
            or 0
        )
        memories = int(
            await session.scalar(
                select(func.count()).select_from(UserMemory).where(UserMemory.user_id == user_id)
            )
            or 0
        )
        sessions = int(
            await session.scalar(
                select(func.count())
                .select_from(RefreshSession)
                .where(RefreshSession.user_id == user_id)
            )
            or 0
        )
        tools = int(
            await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(ToolExecution.user_id == user_id)
            )
            or 0
        )
        return {
            "documents": documents,
            "document_chunks": chunks,
            "conversations": conversations,
            "messages": messages,
            "memories": memories,
            "refresh_sessions": sessions,
            "tool_executions": tools,
        }

    async def _list_storage_keys(self, session: AsyncSession, user_id: uuid.UUID) -> list[str]:
        rows = await session.scalars(
            select(Document.storage_key).where(Document.user_id == user_id)
        )
        return [key for key in rows.all() if key]

    async def _anonymize_tool_executions(self, session: AsyncSession, user_id: uuid.UUID) -> int:
        result = await session.execute(
            update(ToolExecution)
            .where(ToolExecution.user_id == user_id)
            .values(
                user_id=None,
                arguments_json={"redacted": True, "reason": "user_deleted"},
                result_json={"redacted": True, "reason": "user_deleted"},
                error_message=None,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def _cleanup_storage(self, storage_keys: list[str]) -> int:
        if not storage_keys or self.document_service is None:
            return 0 if storage_keys == [] else len(storage_keys)
        failures = 0
        storage = getattr(self.document_service, "storage", None)
        if storage is None:
            return len(storage_keys)
        for key in storage_keys:
            try:
                await storage.delete(key=key)
            except Exception:  # noqa: BLE001
                failures += 1
                logger.warning("user_deletion_storage_delete_failed")
        return failures
