"""Long-term memory service — ownership, lifecycle, conflicts, and settings."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.embeddings.base import EmbeddingProvider
from app.memory.exceptions import (
    MemoryAmbiguousForgetError,
    MemoryLimitExceededError,
    MemoryNotFoundError,
    MemoryValidationError,
)
from app.memory.policies import (
    conversation_memory_active,
    initial_status_for_create,
    is_preference_conflict,
    should_require_confirmation,
)
from app.memory.repository import MemoryRepository
from app.memory.sanitizer import MemorySanitizer
from app.memory.schemas import (
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemorySettingsResponse,
    MemorySettingsUpdateRequest,
    MemoryUpdateRequest,
)
from app.models.enums import (
    MemoryAuditEventType,
    MemoryCategory,
    MemoryConfidence,
    MemorySource,
    MemoryStatus,
)
from app.models.memory import UserMemory, UserMemorySettings
from app.models.user import User

logger = logging.getLogger("cortexa.memory")


class MemoryService:
    def __init__(
        self,
        settings: Settings,
        repository: MemoryRepository | None = None,
        sanitizer: MemorySanitizer | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or MemoryRepository(settings)
        self.sanitizer = sanitizer or MemorySanitizer(
            max_content_characters=settings.memory_max_content_characters,
            max_title_characters=settings.memory_title_max_characters,
        )
        self.embedding_provider = embedding_provider

    def to_response(self, memory: UserMemory) -> MemoryResponse:
        return MemoryResponse.model_validate(memory)

    async def get_settings(
        self,
        session: AsyncSession,
        user: User,
    ) -> MemorySettingsResponse:
        row = await self.repository.get_or_create_settings(session, user)
        return MemorySettingsResponse.model_validate(row)

    async def update_settings(
        self,
        session: AsyncSession,
        user: User,
        request: MemorySettingsUpdateRequest,
    ) -> MemorySettingsResponse:
        row = await self.repository.get_or_create_settings(session, user)
        data = request.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(UTC)
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.updated,
            safe_metadata={"scope": "settings", "fields": sorted(data.keys())},
            correlation_id=request_id_ctx.get(),
        )
        return MemorySettingsResponse.model_validate(row)

    async def list_memories(
        self,
        session: AsyncSession,
        user: User,
        *,
        status: MemoryStatus | None = None,
        category: MemoryCategory | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> MemoryListResponse:
        items, total = await self.repository.list_owned(
            session,
            user,
            status=status,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
        )
        return MemoryListResponse(
            items=[self.to_response(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_memory(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> MemoryResponse:
        memory = await self._require_owned(session, user, memory_id)
        return self.to_response(memory)

    async def create_memory(
        self,
        session: AsyncSession,
        user: User,
        request: MemoryCreateRequest,
        *,
        source: MemorySource = MemorySource.explicit_user_request,
        confidence: MemoryConfidence | None = MemoryConfidence.high,
        source_conversation_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
        force_proposed: bool | None = None,
    ) -> UserMemory:
        settings = await self.repository.get_or_create_settings(session, user)
        cleaned = self.sanitizer.sanitize_for_storage(title=request.title, content=request.content)

        duplicate = await self.repository.find_exact_duplicate(
            session, user, cleaned.normalized_content
        )
        if duplicate is not None:
            raise MemoryValidationError(
                "An identical memory already exists",
                code="memory_duplicate",
            )

        # Semantic near-duplicate when embeddings available.
        embedding = await self._embed(cleaned.content)
        if embedding is not None:
            similar = await self.repository.find_similar_by_embedding(
                session,
                user,
                embedding,
                min_similarity=self.settings.memory_duplicate_similarity_threshold,
                limit=3,
            )
            for existing, score in similar:
                threshold = self.settings.memory_duplicate_similarity_threshold
                if existing.category == request.category and score >= threshold:
                    if is_preference_conflict(existing.category, request.category):
                        await self._supersede(
                            session,
                            user,
                            existing,
                            reason="near_duplicate_conflict",
                        )
                    else:
                        raise MemoryValidationError(
                            "A very similar memory already exists",
                            code="memory_duplicate",
                        )

        # Preference/instruction conflicts: explicit new supersedes old.
        if request.category in {MemoryCategory.preference, MemoryCategory.instruction}:
            for existing in await self.repository.find_active_by_category(
                session, user, request.category
            ):
                if self._looks_like_conflict(existing, cleaned.content):
                    await self._supersede(session, user, existing, reason="preference_superseded")

        confirmation_required = (
            force_proposed
            if force_proposed is not None
            else (
                request.confirmation_required
                if request.confirmation_required is not None
                else should_require_confirmation(
                    source=source,
                    require_confirmation_setting=settings.require_confirmation,
                    confidence=confidence,
                )
            )
        )
        status = initial_status_for_create(confirmation_required=bool(confirmation_required))

        if status == MemoryStatus.active:
            active_count = await self.repository.count_active(session, user)
            max_active = min(
                settings.maximum_active_memories,
                self.settings.memory_max_active_per_user,
            )
            if active_count >= max_active:
                raise MemoryLimitExceededError(f"Active memory limit of {max_active} reached")

        expires_at = request.expires_at
        if expires_at is None and settings.default_expiration_days:
            expires_at = datetime.now(UTC) + timedelta(days=settings.default_expiration_days)

        now = datetime.now(UTC)
        memory = UserMemory(
            id=uuid.uuid4(),
            user_id=user.id,
            category=request.category,
            status=status,
            title=cleaned.title,
            content=cleaned.content,
            normalized_content=cleaned.normalized_content,
            source=source,
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            confidence=confidence,
            importance=request.importance,
            confirmation_required=bool(confirmation_required),
            confirmed_at=now if status == MemoryStatus.active else None,
            expires_at=expires_at,
            embedding=embedding,
            version=1,
        )
        session.add(memory)
        await session.flush()

        event_type = (
            MemoryAuditEventType.proposed
            if status == MemoryStatus.proposed
            else MemoryAuditEventType.created
        )
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=event_type,
            memory_id=memory.id,
            conversation_id=source_conversation_id,
            message_id=source_message_id,
            safe_metadata={
                "category": memory.category.value,
                "source": memory.source.value,
                "status": memory.status.value,
            },
            correlation_id=request_id_ctx.get(),
        )
        logger.info(
            "memory_created user_id=%s memory_id=%s status=%s source=%s",
            user.id,
            memory.id,
            memory.status.value,
            memory.source.value,
        )
        return memory

    async def propose_candidate(
        self,
        session: AsyncSession,
        user: User,
        *,
        title: str,
        content: str,
        category: MemoryCategory,
        confidence: MemoryConfidence,
        importance: float,
        source: MemorySource,
        source_conversation_id: uuid.UUID | None = None,
        source_message_id: uuid.UUID | None = None,
    ) -> UserMemory | None:
        try:
            return await self.create_memory(
                session,
                user,
                MemoryCreateRequest(
                    title=title,
                    content=content,
                    category=category,
                    importance=importance,
                ),
                source=source,
                confidence=confidence,
                source_conversation_id=source_conversation_id,
                source_message_id=source_message_id,
                force_proposed=True,
            )
        except Exception:
            logger.info(
                "memory_propose_skipped user_id=%s category=%s",
                user.id,
                category.value,
            )
            return None

    async def confirm(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> MemoryResponse:
        memory = await self._require_owned(session, user, memory_id)
        if memory.status != MemoryStatus.proposed:
            raise MemoryValidationError("Only proposed memories can be confirmed")
        settings = await self.repository.get_or_create_settings(session, user)
        active_count = await self.repository.count_active(session, user)
        max_active = min(settings.maximum_active_memories, self.settings.memory_max_active_per_user)
        if active_count >= max_active:
            raise MemoryLimitExceededError(f"Active memory limit of {max_active} reached")
        now = datetime.now(UTC)
        memory.status = MemoryStatus.active
        memory.confirmed_at = now
        memory.confirmation_required = False
        memory.updated_at = now
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.confirmed,
            memory_id=memory.id,
            safe_metadata={"status": "active"},
            correlation_id=request_id_ctx.get(),
        )
        return self.to_response(memory)

    async def reject(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> MemoryResponse:
        memory = await self._require_owned(session, user, memory_id)
        if memory.status not in {MemoryStatus.proposed, MemoryStatus.active}:
            raise MemoryValidationError("Memory cannot be rejected in its current state")
        memory.status = MemoryStatus.rejected
        memory.updated_at = datetime.now(UTC)
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.rejected,
            memory_id=memory.id,
            correlation_id=request_id_ctx.get(),
        )
        return self.to_response(memory)

    async def archive(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> MemoryResponse:
        memory = await self._require_owned(session, user, memory_id)
        if memory.status != MemoryStatus.active:
            raise MemoryValidationError("Only active memories can be archived")
        now = datetime.now(UTC)
        memory.status = MemoryStatus.archived
        memory.archived_at = now
        memory.updated_at = now
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.archived,
            memory_id=memory.id,
            correlation_id=request_id_ctx.get(),
        )
        return self.to_response(memory)

    async def restore(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> MemoryResponse:
        memory = await self._require_owned(session, user, memory_id)
        if memory.status != MemoryStatus.archived:
            raise MemoryValidationError("Only archived memories can be restored")
        settings = await self.repository.get_or_create_settings(session, user)
        active_count = await self.repository.count_active(session, user)
        max_active = min(settings.maximum_active_memories, self.settings.memory_max_active_per_user)
        if active_count >= max_active:
            raise MemoryLimitExceededError(f"Active memory limit of {max_active} reached")
        memory.status = MemoryStatus.active
        memory.archived_at = None
        memory.updated_at = datetime.now(UTC)
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.restored,
            memory_id=memory.id,
            correlation_id=request_id_ctx.get(),
        )
        return self.to_response(memory)

    async def update_memory(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
        request: MemoryUpdateRequest,
    ) -> MemoryResponse:
        memory = await self._require_owned(session, user, memory_id)
        if memory.status in {MemoryStatus.deleted, MemoryStatus.rejected}:
            raise MemoryValidationError("Deleted or rejected memories cannot be updated")
        data = request.model_dump(exclude_unset=True)
        title = data.get("title", memory.title)
        content = data.get("content", memory.content)
        cleaned = self.sanitizer.sanitize_for_storage(title=title, content=content)
        memory.title = cleaned.title
        memory.content = cleaned.content
        memory.normalized_content = cleaned.normalized_content
        if "category" in data and data["category"] is not None:
            memory.category = data["category"]
        if "importance" in data and data["importance"] is not None:
            memory.importance = data["importance"]
        if "expires_at" in data:
            memory.expires_at = data["expires_at"]
        memory.version += 1
        memory.updated_at = datetime.now(UTC)
        memory.embedding = await self._embed(cleaned.content)
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.updated,
            memory_id=memory.id,
            safe_metadata={"fields": sorted(data.keys()), "version": memory.version},
            correlation_id=request_id_ctx.get(),
        )
        return self.to_response(memory)

    async def delete_memory(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> None:
        memory = await self._require_owned(session, user, memory_id)
        await self.repository.soft_delete(session, memory, redact_content=True)
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.deleted,
            memory_id=memory.id,
            safe_metadata={"redacted": True},
            correlation_id=request_id_ctx.get(),
        )

    async def remember_explicit(
        self,
        session: AsyncSession,
        user: User,
        payload: str,
        *,
        category: MemoryCategory | None = None,
        conversation_id: uuid.UUID | None = None,
        message_id: uuid.UUID | None = None,
    ) -> UserMemory:
        title = payload.strip()[:80] or "Remembered preference"
        return await self.create_memory(
            session,
            user,
            MemoryCreateRequest(
                title=title if len(title) <= 80 else "Remembered preference",
                content=payload.strip(),
                category=category or MemoryCategory.preference,
                importance=0.8,
            ),
            source=MemorySource.explicit_user_request,
            confidence=MemoryConfidence.high,
            source_conversation_id=conversation_id,
            source_message_id=message_id,
        )

    async def forget_matching(
        self,
        session: AsyncSession,
        user: User,
        query: str,
        *,
        conversation_id: uuid.UUID | None = None,
    ) -> list[UserMemory]:
        matches = await self.repository.search_keyword(
            session,
            user,
            query,
            limit=10,
        )
        if not matches:
            # Broader token search
            tokens = [t for t in query.lower().split() if len(t) > 2][:5]
            seen: dict[uuid.UUID, UserMemory] = {}
            for token in tokens:
                for memory in await self.repository.search_keyword(session, user, token, limit=5):
                    seen[memory.id] = memory
            matches = list(seen.values())

        if not matches:
            raise MemoryNotFoundError()
        if len(matches) > 1:
            # If one clearly dominates keyword match, prefer it.
            scored = sorted(
                matches,
                key=lambda m: _overlap_score(query, f"{m.title} {m.content}"),
                reverse=True,
            )
            if (
                len(scored) >= 2
                and _overlap_score(query, f"{scored[0].title} {scored[0].content}")
                <= _overlap_score(query, f"{scored[1].title} {scored[1].content}") + 0.05
            ):
                raise MemoryAmbiguousForgetError(
                    "Multiple memories match. Please clarify which one to forget.",
                    matches=[
                        {
                            "title": m.title,
                            "category": m.category.value,
                            "loc": ["memory"],
                            "msg": m.title,
                            "type": "memory_match",
                        }
                        for m in scored[:5]
                    ],
                )
            matches = [scored[0]]

        forgotten: list[UserMemory] = []
        for memory in matches:
            await self.archive(session, user, memory.id)
            forgotten.append(memory)
            await self.repository.add_audit(
                session,
                user_id=user.id,
                event_type=MemoryAuditEventType.archived,
                memory_id=memory.id,
                conversation_id=conversation_id,
                safe_metadata={"reason": "explicit_forget"},
                correlation_id=request_id_ctx.get(),
            )
        return forgotten

    async def list_for_prompt(
        self,
        session: AsyncSession,
        user: User,
        *,
        query: str | None = None,
        limit: int = 20,
    ) -> list[UserMemory]:
        if query:
            return await self.repository.search_keyword(session, user, query, limit=limit)
        items, _ = await self.repository.list_owned(
            session,
            user,
            status=MemoryStatus.active,
            limit=limit,
            offset=0,
        )
        return items

    def is_memory_active_for_conversation(
        self,
        settings: UserMemorySettings,
        *,
        conversation_override: bool | None,
        platform_enabled: bool | None = None,
    ) -> bool:
        enabled = self.settings.memory_enabled if platform_enabled is None else platform_enabled
        if not enabled:
            return False
        return conversation_memory_active(
            global_enabled=settings.memory_enabled,
            include_in_chat=settings.include_memories_in_chat,
            conversation_override=conversation_override,
        )

    async def _require_owned(
        self,
        session: AsyncSession,
        user: User,
        memory_id: uuid.UUID,
    ) -> UserMemory:
        memory = await self.repository.get_owned(session, user, memory_id)
        if memory is None:
            raise MemoryNotFoundError()
        return memory

    async def _supersede(
        self,
        session: AsyncSession,
        user: User,
        existing: UserMemory,
        *,
        reason: str,
    ) -> None:
        now = datetime.now(UTC)
        existing.status = MemoryStatus.archived
        existing.archived_at = now
        existing.updated_at = now
        await session.flush()
        await self.repository.add_audit(
            session,
            user_id=user.id,
            event_type=MemoryAuditEventType.conflict_superseded,
            memory_id=existing.id,
            safe_metadata={"reason": reason},
            correlation_id=request_id_ctx.get(),
        )

    def _looks_like_conflict(self, existing: UserMemory, new_content: str) -> bool:
        old = existing.normalized_content
        new = self.sanitizer.normalize_content(new_content)
        # Same topic keywords about language / examples / timezone, etc.
        topic_markers = (
            "prefer",
            "example",
            "language",
            "timezone",
            "python",
            "javascript",
            "typescript",
            "concise",
        )
        old_hits = {m for m in topic_markers if m in old}
        new_hits = {m for m in topic_markers if m in new}
        if old_hits & new_hits and old != new:
            return True
        # High token overlap but different content → likely update.
        old_tokens = set(old.split())
        new_tokens = set(new.split())
        if not old_tokens or not new_tokens:
            return False
        overlap = len(old_tokens & new_tokens) / max(len(old_tokens), len(new_tokens))
        return overlap >= 0.35 and old != new

    async def _embed(self, content: str) -> list[float] | None:
        if self.embedding_provider is None:
            return None
        try:
            return await self.embedding_provider.embed(
                content[: self.settings.embedding_max_input_characters]
            )
        except Exception:
            return None


def _overlap_score(query: str, content: str) -> float:
    q = {t for t in query.lower().split() if len(t) > 2}
    c = {t for t in content.lower().split() if len(t) > 2}
    if not q or not c:
        return 0.0
    return len(q & c) / max(1, len(q))
