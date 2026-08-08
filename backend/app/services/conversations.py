"""Conversation CRUD, search, archive, title, and summary orchestration."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.conversations.exceptions import (
    ConversationArchivedError,
    ConversationNotFoundError,
    InvalidConversationTitleError,
)
from app.conversations.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummaryResponse,
    MessageCitationResponse,
    MessageResponse,
    sanitize_title,
)
from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.models.agent import AgentRun
from app.models.conversation import (
    DEFAULT_CONVERSATION_TITLE,
    Conversation,
    Message,
    MessageCitation,
)
from app.models.enums import AgentRunStatus, ConversationStatus, MessageRole
from app.models.feedback import MessageFeedback
from app.models.tool_execution import ToolExecution
from app.models.user import User
from app.services.tools import execution_to_summary
from app.feedback_schemas import MessageFeedbackView

logger = logging.getLogger("cortexa.conversations")

_WHITESPACE = re.compile(r"\s+")


def conversation_to_summary(conversation: Conversation) -> ConversationSummaryResponse:
    preview = None
    if conversation.summary:
        preview = conversation.summary.strip()
        if len(preview) > 160:
            preview = preview[:160].rstrip() + "…"
    memory_enabled = conversation.memory_enabled_override
    return ConversationSummaryResponse(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status.value,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_message_at=conversation.last_message_at,
        archived_at=conversation.archived_at,
        title_is_auto=conversation.title_is_auto,
        summary_preview=preview,
        memory_enabled=memory_enabled,
    )


def citation_to_response(citation: MessageCitation) -> MessageCitationResponse:
    from app.conversations.citations import message_citation_to_response

    return message_citation_to_response(citation)


def message_to_response(
    message: Message,
    *,
    tool_executions: list[Any] | None = None,
) -> MessageResponse:
    citations = [citation_to_response(item) for item in (message.citations or [])]
    citations.sort(key=lambda item: item.citation_index)
    meta = message.message_metadata or {}
    raw_ids = meta.get("tool_execution_ids") if isinstance(meta, dict) else None
    tool_ids = [str(item) for item in raw_ids] if isinstance(raw_ids, list) else []
    agent_run_id = meta.get("agent_run_id") if isinstance(meta, dict) else None
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role.value,
        content=message.content,
        status=message.status.value,
        sequence_number=message.sequence_number,
        is_active=message.is_active,
        grounded=message.grounded,
        model=message.model,
        provider=message.provider,
        prompt_tokens=message.prompt_tokens,
        completion_tokens=message.completion_tokens,
        total_tokens=message.total_tokens,
        latency_ms=message.latency_ms,
        finish_reason=message.finish_reason,
        error_code=message.error_code,
        regenerated_from_message_id=message.regenerated_from_message_id,
        edited_from_message_id=message.edited_from_message_id,
        created_at=message.created_at,
        updated_at=message.updated_at,
        citations=citations,
        tool_execution_ids=tool_ids,
        tool_executions=list(tool_executions or []),
        agent_run_id=str(agent_run_id) if agent_run_id else None,
        feedback=(
            MessageFeedbackView(
                id=message.feedback.id,
                sentiment=message.feedback.sentiment,
                reason=message.feedback.reason,
                comment=message.feedback.comment,
                status=message.feedback.status,
                created_at=message.feedback.created_at,
                updated_at=message.feedback.updated_at,
            )
            if message.feedback is not None
            else None
        ),
    )


class ConversationService:
    """Own conversation lifecycle operations for the authenticated user."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_conversation(
        self,
        session: AsyncSession,
        user: User,
        request: ConversationCreateRequest,
    ) -> Conversation:
        title = request.title or DEFAULT_CONVERSATION_TITLE
        title_is_auto = request.title is None
        scope = None
        if request.document_ids is not None:
            scope = [str(item) for item in request.document_ids]

        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user.id,
            title=title,
            title_is_auto=title_is_auto,
            status=ConversationStatus.active,
            message_count=0,
            default_document_scope=scope,
        )
        session.add(conversation)
        await session.flush()
        logger.info(
            "conversation_created user_id=%s conversation_id=%s request_id=%s",
            user.id,
            conversation.id,
            request_id_ctx.get() or "-",
        )
        return conversation

    async def get_owned_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Conversation:
        stmt: Select[tuple[Conversation]] = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        conversation = await session.scalar(stmt)
        if conversation is None:
            raise ConversationNotFoundError()
        return conversation

    async def require_active_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Conversation:
        conversation = await self.get_owned_conversation(
            session,
            user,
            conversation_id,
            for_update=for_update,
        )
        if conversation.status == ConversationStatus.archived:
            raise ConversationArchivedError()
        return conversation

    async def list_conversations(
        self,
        session: AsyncSession,
        user: User,
        *,
        limit: int | None = None,
        offset: int = 0,
        include_archived: bool = False,
        status: ConversationStatus | None = None,
        q: str | None = None,
    ) -> ConversationListResponse:
        resolved_limit = (
            limit if limit is not None else self.settings.conversation_list_default_limit
        )
        resolved_limit = max(1, min(resolved_limit, self.settings.conversation_list_max_limit))
        offset = max(0, offset)

        filters = [Conversation.user_id == user.id]
        if status is not None:
            filters.append(Conversation.status == status)
        elif not include_archived:
            filters.append(Conversation.status == ConversationStatus.active)

        search = (q or "").strip()
        if search:
            if len(search) > 200:
                search = search[:200]
            pattern = f"%{search}%"
            message_match = (
                select(Message.conversation_id)
                .where(
                    Message.user_id == user.id,
                    Message.is_active.is_(True),
                    Message.role.in_([MessageRole.user, MessageRole.assistant]),
                    Message.content.ilike(pattern),
                )
                .distinct()
            )
            filters.append(
                or_(
                    Conversation.title.ilike(pattern),
                    Conversation.id.in_(message_match),
                )
            )
            resolved_limit = min(resolved_limit, self.settings.conversation_search_max_results)

        count_stmt = select(func.count()).select_from(Conversation).where(*filters)
        total = int(await session.scalar(count_stmt) or 0)

        stmt = (
            select(Conversation)
            .where(*filters)
            .order_by(
                Conversation.last_message_at.desc().nullslast(),
                Conversation.updated_at.desc(),
                Conversation.created_at.desc(),
            )
            .offset(offset)
            .limit(resolved_limit)
        )
        rows = (await session.scalars(stmt)).all()
        return ConversationListResponse(
            items=[conversation_to_summary(item) for item in rows],
            total=total,
            limit=resolved_limit,
            offset=offset,
        )

    async def get_conversation_detail(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        *,
        message_limit: int = 100,
        include_inactive: bool = False,
    ) -> ConversationDetailResponse:
        conversation = await self.get_owned_conversation(session, user, conversation_id)
        filters = [
            Message.conversation_id == conversation.id,
            Message.user_id == user.id,
        ]
        if not include_inactive:
            filters.append(Message.is_active.is_(True))

        total_messages = int(
            await session.scalar(select(func.count()).select_from(Message).where(*filters)) or 0
        )
        limit = max(1, min(message_limit, 200))
        # Load newest page then present ascending for chat UI.
        newest = (
            await session.scalars(
                select(Message)
                .where(*filters)
                .options(selectinload(Message.citations), selectinload(Message.feedback))
                .order_by(Message.sequence_number.desc())
                .limit(limit)
            )
        ).all()
        messages = list(reversed(newest))

        message_ids = [item.id for item in messages]
        executions_by_message: dict[uuid.UUID, list[Any]] = {mid: [] for mid in message_ids}
        if message_ids:
            exec_rows = (
                await session.scalars(
                    select(ToolExecution)
                    .where(
                        ToolExecution.user_id == user.id,
                        ToolExecution.message_id.in_(message_ids),
                    )
                    .order_by(ToolExecution.created_at.asc())
                )
            ).all()
            for row in exec_rows:
                if row.message_id is not None:
                    executions_by_message.setdefault(row.message_id, []).append(
                        execution_to_summary(row)
                    )

        scope = None
        if conversation.default_document_scope is not None:
            scope = [uuid.UUID(str(item)) for item in conversation.default_document_scope]

        active_agent_run_id = await session.scalar(
            select(AgentRun.id)
            .where(
                AgentRun.user_id == user.id,
                AgentRun.conversation_id == conversation.id,
                AgentRun.status.in_(
                    [
                        AgentRunStatus.pending,
                        AgentRunStatus.planning,
                        AgentRunStatus.running,
                        AgentRunStatus.awaiting_approval,
                    ]
                ),
            )
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )

        return ConversationDetailResponse(
            id=conversation.id,
            title=conversation.title,
            status=conversation.status.value,
            message_count=conversation.message_count,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            last_message_at=conversation.last_message_at,
            archived_at=conversation.archived_at,
            title_is_auto=conversation.title_is_auto,
            summary=conversation.summary,
            default_document_scope=scope,
            messages=[
                message_to_response(
                    item,
                    tool_executions=executions_by_message.get(item.id, []),
                )
                for item in messages
            ],
            has_more_messages=total_messages > len(messages),
            memory_enabled=conversation.memory_enabled_override,
            memory_context_used=int(conversation.memory_context_used or 0),
            active_agent_run_id=active_agent_run_id,
        )

    async def set_memory_enabled(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        *,
        memory_enabled: bool,
        reason: str | None = None,
    ) -> Conversation:
        conversation = await self.get_owned_conversation(session, user, conversation_id)
        conversation.memory_enabled_override = memory_enabled
        conversation.memory_disabled_reason = None if memory_enabled else (reason or "user_toggle")
        await session.flush()
        return conversation

    async def rename_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        title: str,
    ) -> Conversation:
        conversation = await self.get_owned_conversation(session, user, conversation_id)
        try:
            cleaned = sanitize_title(
                title,
                max_length=self.settings.conversation_title_max_characters,
            )
        except ValueError as exc:
            raise InvalidConversationTitleError(str(exc)) from exc
        conversation.title = cleaned
        conversation.title_is_auto = False
        conversation.updated_at = datetime.now(UTC)
        await session.flush()
        logger.info(
            "conversation_renamed user_id=%s conversation_id=%s request_id=%s",
            user.id,
            conversation.id,
            request_id_ctx.get() or "-",
        )
        return conversation

    async def archive_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
    ) -> Conversation:
        conversation = await self.get_owned_conversation(session, user, conversation_id)
        conversation.status = ConversationStatus.archived
        conversation.archived_at = datetime.now(UTC)
        conversation.updated_at = datetime.now(UTC)
        await session.flush()
        logger.info(
            "conversation_archived user_id=%s conversation_id=%s request_id=%s",
            user.id,
            conversation.id,
            request_id_ctx.get() or "-",
        )
        return conversation

    async def unarchive_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
    ) -> Conversation:
        conversation = await self.get_owned_conversation(session, user, conversation_id)
        conversation.status = ConversationStatus.active
        conversation.archived_at = None
        conversation.updated_at = datetime.now(UTC)
        await session.flush()
        logger.info(
            "conversation_unarchived user_id=%s conversation_id=%s request_id=%s",
            user.id,
            conversation.id,
            request_id_ctx.get() or "-",
        )
        return conversation

    async def delete_conversation(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
    ) -> None:
        conversation = await self.get_owned_conversation(session, user, conversation_id)
        await session.delete(conversation)
        await session.flush()
        logger.info(
            "conversation_deleted user_id=%s conversation_id=%s request_id=%s",
            user.id,
            conversation_id,
            request_id_ctx.get() or "-",
        )

    async def refresh_counters(
        self,
        session: AsyncSession,
        conversation: Conversation,
    ) -> None:
        active_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.is_active.is_(True),
                )
            )
            or 0
        )
        last_at = await session.scalar(
            select(func.max(Message.created_at)).where(
                Message.conversation_id == conversation.id,
                Message.is_active.is_(True),
            )
        )
        conversation.message_count = active_count
        conversation.last_message_at = last_at
        conversation.updated_at = datetime.now(UTC)
        await session.flush()

    def sanitize_generated_title(self, raw: str) -> str:
        cleaned = _WHITESPACE.sub(" ", raw).strip().strip("\"'`")
        cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)
        max_len = self.settings.conversation_title_max_characters
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rstrip()
        return cleaned or DEFAULT_CONVERSATION_TITLE
