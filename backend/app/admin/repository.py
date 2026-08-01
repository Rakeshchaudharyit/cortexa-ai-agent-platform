"""Data access for enterprise administration queries."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Date, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.exceptions import AdminNotFoundError
from app.models.admin import AdminAuditEvent, PlatformSetting, ToolConfiguration
from app.models.conversation import Conversation, Message
from app.models.document import Document, DocumentChunk
from app.models.enums import (
    DocumentStatus,
    MemoryStatus,
    MessageStatus,
    ToolExecutionStatus,
    UserRole,
    UserStatus,
)
from app.models.memory import MemoryAuditEvent, UserMemory
from app.models.refresh_session import RefreshSession
from app.models.tool_execution import ToolExecution
from app.models.user import User


class AdminRepository:
    """Read/write helpers for admin aggregates and listings."""

    # ── Users ──────────────────────────────────────────────────────────────

    async def count_active_admins(self, session: AsyncSession) -> int:
        value = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.admin, User.status == UserStatus.active)
        )
        return int(value or 0)

    async def get_user(self, session: AsyncSession, user_id: uuid.UUID) -> User:
        user = await session.get(User, user_id)
        if user is None:
            raise AdminNotFoundError("User not found")
        return user

    def _user_count_subqueries(self) -> tuple[Any, Any, Any]:
        conv = (
            select(Conversation.user_id, func.count().label("conversations_count"))
            .group_by(Conversation.user_id)
            .subquery()
        )
        docs = (
            select(Document.user_id, func.count().label("documents_count"))
            .group_by(Document.user_id)
            .subquery()
        )
        mems = (
            select(UserMemory.user_id, func.count().label("memories_count"))
            .where(UserMemory.status != MemoryStatus.deleted)
            .group_by(UserMemory.user_id)
            .subquery()
        )
        return conv, docs, mems

    async def list_users(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
        role: UserRole | None = None,
        status: UserStatus | None = None,
        verified: bool | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        conv, docs, mems = self._user_count_subqueries()
        filters: list[Any] = []
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(User.email).like(term),
                    func.lower(User.full_name).like(term),
                )
            )
        if role is not None:
            filters.append(User.role == role)
        if status is not None:
            filters.append(User.status == status)
        if verified is not None:
            filters.append(User.is_email_verified.is_(verified))
        if created_from is not None:
            filters.append(User.created_at >= created_from)
        if created_to is not None:
            filters.append(User.created_at <= created_to)

        total = int(
            await session.scalar(select(func.count()).select_from(User).where(*filters)) or 0
        )
        stmt = (
            select(
                User,
                func.coalesce(conv.c.conversations_count, 0),
                func.coalesce(docs.c.documents_count, 0),
                func.coalesce(mems.c.memories_count, 0),
            )
            .outerjoin(conv, conv.c.user_id == User.id)
            .outerjoin(docs, docs.c.user_id == User.id)
            .outerjoin(mems, mems.c.user_id == User.id)
            .where(*filters)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        items = [
            {
                "user": user,
                "conversations_count": int(c or 0),
                "documents_count": int(d or 0),
                "memories_count": int(m or 0),
            }
            for user, c, d, m in rows
        ]
        return items, total

    async def user_resource_counts(
        self, session: AsyncSession, user_id: uuid.UUID
    ) -> dict[str, int]:
        conversations = int(
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == user_id)
            )
            or 0
        )
        documents = int(
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.user_id == user_id)
            )
            or 0
        )
        memories = int(
            await session.scalar(
                select(func.count())
                .select_from(UserMemory)
                .where(UserMemory.user_id == user_id, UserMemory.status != MemoryStatus.deleted)
            )
            or 0
        )
        tool_total = int(
            await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(ToolExecution.user_id == user_id)
            )
            or 0
        )
        tool_ok = int(
            await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(
                    ToolExecution.user_id == user_id,
                    ToolExecution.status == ToolExecutionStatus.succeeded,
                )
            )
            or 0
        )
        tool_fail = int(
            await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(
                    ToolExecution.user_id == user_id,
                    ToolExecution.status.in_(
                        [
                            ToolExecutionStatus.failed,
                            ToolExecutionStatus.timed_out,
                            ToolExecutionStatus.denied,
                        ]
                    ),
                )
            )
            or 0
        )
        sessions = int(
            await session.scalar(
                select(func.count())
                .select_from(RefreshSession)
                .where(
                    RefreshSession.user_id == user_id,
                    RefreshSession.revoked_at.is_(None),
                    RefreshSession.expires_at > func.now(),
                )
            )
            or 0
        )
        return {
            "conversations_count": conversations,
            "documents_count": documents,
            "memories_count": memories,
            "tool_executions_count": tool_total,
            "tool_success_count": tool_ok,
            "tool_failure_count": tool_fail,
            "active_sessions_count": sessions,
        }

    # ── Documents ──────────────────────────────────────────────────────────

    async def list_documents(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        owner_id: uuid.UUID | None = None,
        status: DocumentStatus | None = None,
        media_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[tuple[Document, User]], int]:
        filters: list[Any] = []
        if owner_id is not None:
            filters.append(Document.user_id == owner_id)
        if status is not None:
            filters.append(Document.status == status)
        if media_type and media_type.strip():
            filters.append(Document.media_type.ilike(f"%{media_type.strip()}%"))
        if created_from is not None:
            filters.append(Document.created_at >= created_from)
        if created_to is not None:
            filters.append(Document.created_at <= created_to)
        total = int(
            await session.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
        )
        stmt = (
            select(Document, User)
            .join(User, User.id == Document.user_id)
            .where(*filters)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).all())
        return [(doc, user) for doc, user in rows], total

    async def get_document(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> tuple[Document, User]:
        row = (
            await session.execute(
                select(Document, User)
                .join(User, User.id == Document.user_id)
                .where(Document.id == document_id)
            )
        ).one_or_none()
        if row is None:
            raise AdminNotFoundError("Document not found")
        return row[0], row[1]

    async def sample_chunk_excerpts(
        self, session: AsyncSession, document_id: uuid.UUID, *, limit: int = 3
    ) -> list[str]:
        rows = await session.scalars(
            select(DocumentChunk.content)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(limit)
        )
        out: list[str] = []
        for content in rows.all():
            text = (content or "").strip().replace("\n", " ")
            if text:
                out.append(text[:180] + ("…" if len(text) > 180 else ""))
        return out

    # ── Conversations ──────────────────────────────────────────────────────

    async def list_conversations(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        owner_id: uuid.UUID | None = None,
        status: Any | None = None,
        activity_from: datetime | None = None,
        activity_to: datetime | None = None,
        grounded: bool | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        msg_counts = (
            select(Message.conversation_id, func.count().label("message_count"))
            .group_by(Message.conversation_id)
            .subquery()
        )
        tool_counts = (
            select(ToolExecution.conversation_id, func.count().label("tool_count"))
            .where(ToolExecution.conversation_id.is_not(None))
            .group_by(ToolExecution.conversation_id)
            .subquery()
        )
        filters: list[Any] = []
        if owner_id is not None:
            filters.append(Conversation.user_id == owner_id)
        if status is not None:
            filters.append(Conversation.status == status)
        if activity_from is not None:
            filters.append(Conversation.updated_at >= activity_from)
        if activity_to is not None:
            filters.append(Conversation.updated_at <= activity_to)
        if grounded is True:
            filters.append(Conversation.default_document_scope.is_not(None))
        if grounded is False:
            filters.append(Conversation.default_document_scope.is_(None))

        total = int(
            await session.scalar(select(func.count()).select_from(Conversation).where(*filters))
            or 0
        )
        stmt = (
            select(
                Conversation,
                User,
                func.coalesce(msg_counts.c.message_count, 0),
                func.coalesce(tool_counts.c.tool_count, 0),
            )
            .join(User, User.id == Conversation.user_id)
            .outerjoin(msg_counts, msg_counts.c.conversation_id == Conversation.id)
            .outerjoin(tool_counts, tool_counts.c.conversation_id == Conversation.id)
            .where(*filters)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        items = [
            {
                "conversation": conv,
                "owner": user,
                "message_count": int(mc or 0),
                "tool_execution_count": int(tc or 0),
            }
            for conv, user, mc, tc in rows
        ]
        return items, total

    async def get_conversation(
        self, session: AsyncSession, conversation_id: uuid.UUID
    ) -> dict[str, Any]:
        row = (
            await session.execute(
                select(Conversation, User)
                .join(User, User.id == Conversation.user_id)
                .where(Conversation.id == conversation_id)
            )
        ).one_or_none()
        if row is None:
            raise AdminNotFoundError("Conversation not found")
        conv, owner = row
        message_count = int(
            await session.scalar(
                select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)
            )
            or 0
        )
        from app.models.conversation import MessageCitation

        citations = int(
            await session.scalar(
                select(func.count())
                .select_from(MessageCitation)
                .join(Message, Message.id == MessageCitation.message_id)
                .where(Message.conversation_id == conv.id)
            )
            or 0
        )
        tool_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(ToolExecution.conversation_id == conv.id)
            )
            or 0
        )
        failed = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conv.id,
                    Message.status == MessageStatus.failed,
                )
            )
            or 0
        )
        avg_latency = await session.scalar(
            select(func.avg(Message.latency_ms)).where(
                Message.conversation_id == conv.id,
                Message.latency_ms.is_not(None),
            )
        )
        tools = list(
            (
                await session.scalars(
                    select(ToolExecution)
                    .where(ToolExecution.conversation_id == conv.id)
                    .order_by(ToolExecution.created_at.desc())
                    .limit(20)
                )
            ).all()
        )
        return {
            "conversation": conv,
            "owner": owner,
            "message_count": message_count,
            "citations_count": citations,
            "tool_execution_count": tool_count,
            "failed_message_count": failed,
            "average_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "tools": tools,
        }

    # ── Memories ───────────────────────────────────────────────────────────

    async def list_memories(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        owner_id: uuid.UUID | None = None,
        category: Any | None = None,
        status: MemoryStatus | None = None,
        source: Any | None = None,
    ) -> tuple[list[tuple[UserMemory, User]], int]:
        filters: list[Any] = [UserMemory.status != MemoryStatus.deleted]
        if owner_id is not None:
            filters.append(UserMemory.user_id == owner_id)
        if category is not None:
            filters.append(UserMemory.category == category)
        if status is not None:
            filters.append(UserMemory.status == status)
        if source is not None:
            filters.append(UserMemory.source == source)
        total = int(
            await session.scalar(select(func.count()).select_from(UserMemory).where(*filters)) or 0
        )
        rows = list(
            (
                await session.execute(
                    select(UserMemory, User)
                    .join(User, User.id == UserMemory.user_id)
                    .where(*filters)
                    .order_by(UserMemory.updated_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        return [(m, u) for m, u in rows], total

    async def get_memory(
        self, session: AsyncSession, memory_id: uuid.UUID
    ) -> tuple[UserMemory, User]:
        row = (
            await session.execute(
                select(UserMemory, User)
                .join(User, User.id == UserMemory.user_id)
                .where(UserMemory.id == memory_id)
            )
        ).one_or_none()
        if row is None:
            raise AdminNotFoundError("Memory not found")
        return row[0], row[1]

    async def memory_audit_events(
        self, session: AsyncSession, memory_id: uuid.UUID, *, limit: int = 20
    ) -> list[MemoryAuditEvent]:
        rows = await session.scalars(
            select(MemoryAuditEvent)
            .where(MemoryAuditEvent.memory_id == memory_id)
            .order_by(MemoryAuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(rows.all())

    # ── Tools / executions ─────────────────────────────────────────────────

    async def tool_execution_stats(self, session: AsyncSession) -> dict[str, dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    ToolExecution.tool_name,
                    func.count().label("total"),
                    func.sum(
                        case(
                            (ToolExecution.status == ToolExecutionStatus.succeeded, 1),
                            else_=0,
                        )
                    ).label("succeeded"),
                    func.avg(ToolExecution.duration_ms).label("avg_duration"),
                ).group_by(ToolExecution.tool_name)
            )
        ).all()
        out: dict[str, dict[str, Any]] = {}
        for name, total, succeeded, avg_duration in rows:
            total_i = int(total or 0)
            ok_i = int(succeeded or 0)
            out[str(name)] = {
                "execution_count": total_i,
                "succeeded": ok_i,
                "success_rate": (ok_i / total_i) if total_i else None,
                "average_duration_ms": float(avg_duration) if avg_duration is not None else None,
            }
        return out

    async def list_tool_configurations(self, session: AsyncSession) -> list[ToolConfiguration]:
        rows = await session.scalars(
            select(ToolConfiguration).order_by(ToolConfiguration.tool_name)
        )
        return list(rows.all())

    async def get_tool_configuration(
        self, session: AsyncSession, tool_name: str
    ) -> ToolConfiguration | None:
        row = await session.scalar(
            select(ToolConfiguration).where(ToolConfiguration.tool_name == tool_name)
        )
        return row if isinstance(row, ToolConfiguration) else None

    async def upsert_tool_configuration(
        self,
        session: AsyncSession,
        *,
        tool_name: str,
        enabled: bool,
        timeout_override: int | None,
        confirmation_required_override: bool | None,
        updated_by_user_id: uuid.UUID | None,
    ) -> ToolConfiguration:
        row = await self.get_tool_configuration(session, tool_name)
        if row is None:
            row = ToolConfiguration(
                id=uuid.uuid4(),
                tool_name=tool_name,
                enabled=enabled,
                timeout_override=timeout_override,
                confirmation_required_override=confirmation_required_override,
                updated_by_user_id=updated_by_user_id,
            )
            session.add(row)
        else:
            row.enabled = enabled
            row.timeout_override = timeout_override
            row.confirmation_required_override = confirmation_required_override
            row.updated_by_user_id = updated_by_user_id
        await session.flush()
        return row

    async def list_tool_executions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        user_id: uuid.UUID | None = None,
        tool_name: str | None = None,
        status: ToolExecutionStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[tuple[ToolExecution, User]], int]:
        filters: list[Any] = []
        if user_id is not None:
            filters.append(ToolExecution.user_id == user_id)
        if tool_name:
            filters.append(ToolExecution.tool_name == tool_name)
        if status is not None:
            filters.append(ToolExecution.status == status)
        if created_from is not None:
            filters.append(ToolExecution.created_at >= created_from)
        if created_to is not None:
            filters.append(ToolExecution.created_at <= created_to)
        total = int(
            await session.scalar(select(func.count()).select_from(ToolExecution).where(*filters))
            or 0
        )
        rows = list(
            (
                await session.execute(
                    select(ToolExecution, User)
                    .join(User, User.id == ToolExecution.user_id)
                    .where(*filters)
                    .order_by(ToolExecution.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
        )
        return [(e, u) for e, u in rows], total

    async def get_tool_execution(
        self, session: AsyncSession, execution_id: uuid.UUID
    ) -> tuple[ToolExecution, User]:
        row = (
            await session.execute(
                select(ToolExecution, User)
                .join(User, User.id == ToolExecution.user_id)
                .where(ToolExecution.id == execution_id)
            )
        ).one_or_none()
        if row is None:
            raise AdminNotFoundError("Tool execution not found")
        return row[0], row[1]

    # ── Settings / audit ───────────────────────────────────────────────────

    async def list_platform_settings(self, session: AsyncSession) -> list[PlatformSetting]:
        rows = await session.scalars(select(PlatformSetting).order_by(PlatformSetting.key))
        return list(rows.all())

    async def upsert_platform_setting(
        self,
        session: AsyncSession,
        *,
        key: str,
        value: Any,
        updated_by_user_id: uuid.UUID | None,
    ) -> PlatformSetting:
        row = await session.scalar(select(PlatformSetting).where(PlatformSetting.key == key))
        if row is None:
            row = PlatformSetting(
                id=uuid.uuid4(),
                key=key,
                value_json=value,
                updated_by_user_id=updated_by_user_id,
            )
            session.add(row)
        else:
            row.value_json = value
            row.updated_by_user_id = updated_by_user_id
        await session.flush()
        return row

    async def list_audit_events(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        actor_user_id: uuid.UUID | None = None,
        action: str | None = None,
        target_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[tuple[AdminAuditEvent, str | None]], int]:
        filters: list[Any] = []
        if actor_user_id is not None:
            filters.append(AdminAuditEvent.actor_user_id == actor_user_id)
        if action:
            filters.append(AdminAuditEvent.action == action)
        if target_type:
            filters.append(AdminAuditEvent.target_type == target_type)
        if created_from is not None:
            filters.append(AdminAuditEvent.created_at >= created_from)
        if created_to is not None:
            filters.append(AdminAuditEvent.created_at <= created_to)
        total = int(
            await session.scalar(select(func.count()).select_from(AdminAuditEvent).where(*filters))
            or 0
        )
        actor = select(User.id, User.email).subquery()
        stmt = (
            select(AdminAuditEvent, actor.c.email)
            .outerjoin(actor, actor.c.id == AdminAuditEvent.actor_user_id)
            .where(*filters)
            .order_by(AdminAuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        return [(event, email) for event, email in rows], total

    # ── Dashboard / analytics metrics ──────────────────────────────────────

    async def dashboard_counts(self, session: AsyncSession) -> dict[str, Any]:
        users_total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
        users_active = int(
            await session.scalar(
                select(func.count()).select_from(User).where(User.status == UserStatus.active)
            )
            or 0
        )
        users_disabled = int(
            await session.scalar(
                select(func.count()).select_from(User).where(User.status == UserStatus.disabled)
            )
            or 0
        )
        docs_total = int(await session.scalar(select(func.count()).select_from(Document)) or 0)
        docs_ready = int(
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.status == DocumentStatus.ready)
            )
            or 0
        )
        docs_failed = int(
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.status == DocumentStatus.failed)
            )
            or 0
        )
        docs_processing = int(
            await session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.status.in_([DocumentStatus.pending, DocumentStatus.processing]))
            )
            or 0
        )
        conversations = int(
            await session.scalar(select(func.count()).select_from(Conversation)) or 0
        )
        from sqlalchemy import text

        messages_24h = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.created_at >= text("NOW() - INTERVAL '24 hours'"))
            )
            or 0
        )
        memories_active = int(
            await session.scalar(
                select(func.count())
                .select_from(UserMemory)
                .where(UserMemory.status == MemoryStatus.active)
            )
            or 0
        )
        tools_total = int(
            await session.scalar(select(func.count()).select_from(ToolExecution)) or 0
        )
        tools_ok = int(
            await session.scalar(
                select(func.count())
                .select_from(ToolExecution)
                .where(ToolExecution.status == ToolExecutionStatus.succeeded)
            )
            or 0
        )
        avg_latency = await session.scalar(
            select(func.avg(Message.latency_ms)).where(Message.latency_ms.is_not(None))
        )
        failed_ai = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.status == MessageStatus.failed)
            )
            or 0
        )
        return {
            "users_total": users_total,
            "users_active": users_active,
            "users_disabled": users_disabled,
            "documents_total": docs_total,
            "documents_ready": docs_ready,
            "documents_failed": docs_failed,
            "documents_processing": docs_processing,
            "conversations_total": conversations,
            "messages_24h": messages_24h,
            "memories_active": memories_active,
            "tool_executions": tools_total,
            "tool_success_rate": (tools_ok / tools_total) if tools_total else None,
            "average_response_time_ms": float(avg_latency) if avg_latency is not None else None,
            "failed_ai_requests": failed_ai,
        }

    async def usage_trend(self, session: AsyncSession, *, days: int = 14) -> list[dict[str, Any]]:
        day_expr = cast(Conversation.created_at, Date)
        conv_rows = (
            await session.execute(
                select(day_expr.label("day"), func.count())
                .where(Conversation.created_at >= text_interval_days(days))
                .group_by("day")
                .order_by("day")
            )
        ).all()
        msg_day = cast(Message.created_at, Date)
        msg_rows = (
            await session.execute(
                select(msg_day.label("day"), func.count())
                .where(Message.created_at >= text_interval_days(days))
                .group_by("day")
                .order_by("day")
            )
        ).all()
        tool_day = cast(ToolExecution.created_at, Date)
        tool_rows = (
            await session.execute(
                select(tool_day.label("day"), func.count())
                .where(ToolExecution.created_at >= text_interval_days(days))
                .group_by("day")
                .order_by("day")
            )
        ).all()
        merged: dict[str, dict[str, int]] = {}
        for day, count in conv_rows:
            key = day.isoformat()
            merged.setdefault(key, {"conversations": 0, "messages": 0, "tool_executions": 0})
            merged[key]["conversations"] = int(count)
        for day, count in msg_rows:
            key = day.isoformat()
            merged.setdefault(key, {"conversations": 0, "messages": 0, "tool_executions": 0})
            merged[key]["messages"] = int(count)
        for day, count in tool_rows:
            key = day.isoformat()
            merged.setdefault(key, {"conversations": 0, "messages": 0, "tool_executions": 0})
            merged[key]["tool_executions"] = int(count)
        return [{"date": day, **merged[day]} for day in sorted(merged)]

    async def recent_platform_activity(
        self, session: AsyncSession, *, limit: int = 15
    ) -> list[dict[str, Any]]:
        audits = list(
            (
                await session.execute(
                    select(AdminAuditEvent, User.email)
                    .outerjoin(User, User.id == AdminAuditEvent.actor_user_id)
                    .order_by(AdminAuditEvent.created_at.desc())
                    .limit(limit)
                )
            ).all()
        )
        items: list[dict[str, Any]] = [
            {
                "kind": "admin_action",
                "summary": event.safe_summary,
                "created_at": event.created_at,
                "actor_email": email,
                "target_type": event.target_type,
            }
            for event, email in audits
        ]
        if len(items) < limit:
            users = list(
                (
                    await session.scalars(
                        select(User).order_by(User.created_at.desc()).limit(limit)
                    )
                ).all()
            )
            for user in users:
                items.append(
                    {
                        "kind": "user_registration",
                        "summary": f"User registered: {user.email}",
                        "created_at": user.created_at,
                        "actor_email": user.email,
                        "target_type": "user",
                    }
                )
        items.sort(key=lambda i: i["created_at"], reverse=True)
        return items[:limit]


def text_interval_days(days: int) -> Any:
    from sqlalchemy import text

    return text(f"NOW() - INTERVAL '{int(days)} days'")
