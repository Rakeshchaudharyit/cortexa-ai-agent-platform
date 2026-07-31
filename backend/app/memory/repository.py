"""SQLAlchemy persistence helpers for long-term memory."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.memory.policies import default_settings_values
from app.models.enums import MemoryAuditEventType, MemoryCategory, MemoryStatus
from app.models.memory import MemoryAuditEvent, UserMemory, UserMemorySettings
from app.models.user import User

_REDACTED_CONTENT = "[redacted]"
_REDACTED_TITLE = "[deleted memory]"


class MemoryRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_owned(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> UserMemory | None:
        stmt = select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user.id,
        )
        if not include_deleted:
            stmt = stmt.where(UserMemory.status != MemoryStatus.deleted)
        result = await session.scalar(stmt)
        return result if isinstance(result, UserMemory) else None

    async def list_owned(
        self,
        session: AsyncSession,
        user: User,
        *,
        status: MemoryStatus | None = None,
        category: MemoryCategory | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> tuple[list[UserMemory], int]:
        filters = [UserMemory.user_id == user.id]
        if not include_deleted:
            filters.append(UserMemory.status != MemoryStatus.deleted)
        if status is not None:
            filters.append(UserMemory.status == status)
        if category is not None:
            filters.append(UserMemory.category == category)
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(UserMemory.title).like(term),
                    func.lower(UserMemory.content).like(term),
                )
            )
        where = and_(*filters)
        total = await session.scalar(select(func.count()).select_from(UserMemory).where(where)) or 0
        rows = await session.scalars(
            select(UserMemory)
            .where(where)
            .order_by(UserMemory.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total)

    async def count_active(self, session: AsyncSession, user: User) -> int:
        now = datetime.now(UTC)
        stmt = (
            select(func.count())
            .select_from(UserMemory)
            .where(
                UserMemory.user_id == user.id,
                UserMemory.status == MemoryStatus.active,
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
            )
        )
        return int(await session.scalar(stmt) or 0)

    async def find_exact_duplicate(
        self,
        session: AsyncSession,
        user: User,
        normalized_content: str,
    ) -> UserMemory | None:
        now = datetime.now(UTC)
        result = await session.scalar(
            select(UserMemory).where(
                UserMemory.user_id == user.id,
                UserMemory.normalized_content == normalized_content,
                UserMemory.status.in_([MemoryStatus.active, MemoryStatus.proposed]),
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
            )
        )
        return result if isinstance(result, UserMemory) else None

    async def find_active_by_category(
        self,
        session: AsyncSession,
        user: User,
        category: MemoryCategory,
    ) -> list[UserMemory]:
        now = datetime.now(UTC)
        rows = await session.scalars(
            select(UserMemory).where(
                UserMemory.user_id == user.id,
                UserMemory.category == category,
                UserMemory.status == MemoryStatus.active,
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
            )
        )
        return list(rows)

    async def find_similar_by_embedding(
        self,
        session: AsyncSession,
        user: User,
        embedding: list[float],
        *,
        min_similarity: float,
        limit: int = 5,
    ) -> list[tuple[UserMemory, float]]:
        now = datetime.now(UTC)
        distance = UserMemory.embedding.cosine_distance(embedding)
        similarity_expr = (1 - distance).label("similarity")
        stmt = (
            select(UserMemory, similarity_expr)
            .where(
                UserMemory.user_id == user.id,
                UserMemory.status.in_([MemoryStatus.active, MemoryStatus.proposed]),
                UserMemory.embedding.is_not(None),
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
            )
            .order_by(distance)
            .limit(limit)
        )
        rows = await session.execute(stmt)
        results: list[tuple[UserMemory, float]] = []
        for memory, similarity in rows.all():
            score = float(similarity)
            if score >= min_similarity:
                results.append((memory, score))
        return results

    async def list_retrievable(
        self,
        session: AsyncSession,
        user: User,
    ) -> list[UserMemory]:
        now = datetime.now(UTC)
        rows = await session.scalars(
            select(UserMemory).where(
                UserMemory.user_id == user.id,
                UserMemory.status == MemoryStatus.active,
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
            )
        )
        return list(rows)

    async def soft_delete(
        self,
        session: AsyncSession,
        memory: UserMemory,
        *,
        redact_content: bool = True,
    ) -> UserMemory:
        now = datetime.now(UTC)
        memory.status = MemoryStatus.deleted
        memory.deleted_at = now
        memory.embedding = None
        if redact_content:
            memory.content = _REDACTED_CONTENT
            memory.title = _REDACTED_TITLE
            memory.normalized_content = _REDACTED_CONTENT
            memory.memory_metadata = {"redacted": True}
        memory.updated_at = now
        await session.flush()
        return memory

    async def get_or_create_settings(
        self,
        session: AsyncSession,
        user: User,
    ) -> UserMemorySettings:
        existing = await session.get(UserMemorySettings, user.id)
        if existing is not None:
            return existing
        values = default_settings_values(self.settings)
        settings = UserMemorySettings(user_id=user.id, **values)
        session.add(settings)
        await session.flush()
        return settings

    async def add_audit(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_type: MemoryAuditEventType,
        memory_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
        safe_metadata: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> MemoryAuditEvent:
        event = MemoryAuditEvent(
            id=uuid.uuid4(),
            user_id=user_id,
            memory_id=memory_id,
            event_type=event_type,
            conversation_id=conversation_id,
            message_id=message_id,
            safe_metadata_json=safe_metadata,
            correlation_id=correlation_id,
        )
        session.add(event)
        await session.flush()
        return event

    async def mark_used(
        self,
        session: AsyncSession,
        memory_ids: list[uuid.UUID],
        user_id: uuid.UUID,
    ) -> None:
        if not memory_ids:
            return
        now = datetime.now(UTC)
        await session.execute(
            update(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.id.in_(memory_ids),
                UserMemory.status == MemoryStatus.active,
            )
            .values(
                use_count=UserMemory.use_count + 1,
                last_used_at=now,
                updated_at=now,
            )
        )

    async def search_keyword(
        self,
        session: AsyncSession,
        user: User,
        query: str,
        *,
        limit: int = 10,
    ) -> list[UserMemory]:
        now = datetime.now(UTC)
        term = f"%{query.strip().lower()}%"
        rows = await session.scalars(
            select(UserMemory)
            .where(
                UserMemory.user_id == user.id,
                UserMemory.status == MemoryStatus.active,
                or_(UserMemory.expires_at.is_(None), UserMemory.expires_at > now),
                or_(
                    func.lower(UserMemory.title).like(term),
                    func.lower(UserMemory.content).like(term),
                    func.lower(UserMemory.normalized_content).like(term),
                ),
            )
            .order_by(UserMemory.importance.desc(), UserMemory.updated_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def list_audit(
        self,
        session: AsyncSession,
        user: User,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[MemoryAuditEvent], int]:
        where = MemoryAuditEvent.user_id == user.id
        total = (
            await session.scalar(select(func.count()).select_from(MemoryAuditEvent).where(where))
            or 0
        )
        rows = await session.scalars(
            select(MemoryAuditEvent)
            .where(where)
            .order_by(MemoryAuditEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total)
