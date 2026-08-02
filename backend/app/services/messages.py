"""Message persistence, sequencing, editing, citations, and regeneration helpers."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.conversations.exceptions import (
    DuplicateClientRequestError,
    MessageEditNotAllowedError,
    MessageNotFoundError,
    MessageRegenerationNotAllowedError,
    MessageTooLargeError,
)
from app.core.config import Settings
from app.core.logging import request_id_ctx
from app.documents.schemas import RagCitation
from app.models.conversation import Conversation, Message, MessageCitation
from app.models.enums import MessageRole, MessageStatus
from app.models.user import User
from app.services.conversations import ConversationService

logger = logging.getLogger("cortexa.messages")


class MessageService:
    """Own message lifecycle operations with concurrency-safe sequencing."""

    def __init__(
        self,
        settings: Settings,
        conversation_service: ConversationService,
    ) -> None:
        self.settings = settings
        self.conversation_service = conversation_service

    async def _next_sequence(
        self,
        session: AsyncSession,
        conversation_id: uuid.UUID,
    ) -> int:
        current = await session.scalar(
            select(func.coalesce(func.max(Message.sequence_number), 0)).where(
                Message.conversation_id == conversation_id
            )
        )
        return int(current or 0) + 1

    def _validate_content(self, content: str) -> str:
        cleaned = content.strip()
        if not cleaned:
            raise MessageTooLargeError("Message content cannot be blank")
        if len(cleaned) > self.settings.message_max_characters:
            raise MessageTooLargeError()
        return cleaned

    async def find_by_client_request_id(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        client_request_id: uuid.UUID,
    ) -> Message | None:
        result = await session.scalar(
            select(Message)
            .options(selectinload(Message.citations))
            .where(
                Message.user_id == user.id,
                Message.conversation_id == conversation_id,
                Message.client_request_id == client_request_id,
            )
        )
        return result if isinstance(result, Message) else None

    async def append_user_message(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
        content: str,
        *,
        client_request_id: uuid.UUID | None = None,
        edited_from_message_id: uuid.UUID | None = None,
    ) -> Message:
        cleaned = self._validate_content(content)
        if client_request_id is not None:
            existing = await self.find_by_client_request_id(
                session,
                user,
                conversation.id,
                client_request_id,
            )
            if existing is not None:
                raise DuplicateClientRequestError()

        sequence = await self._next_sequence(session, conversation.id)
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.user,
            content=cleaned,
            status=MessageStatus.complete,
            sequence_number=sequence,
            is_active=True,
            client_request_id=client_request_id,
            edited_from_message_id=edited_from_message_id,
        )
        session.add(message)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise DuplicateClientRequestError() from exc

        await self.conversation_service.refresh_counters(session, conversation)
        logger.info(
            "user_message_accepted user_id=%s conversation_id=%s message_id=%s "
            "content_length=%s request_id=%s",
            user.id,
            conversation.id,
            message.id,
            len(cleaned),
            request_id_ctx.get() or "-",
        )
        return message

    async def create_pending_assistant(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
        *,
        regenerated_from_message_id: uuid.UUID | None = None,
    ) -> Message:
        # Prevent parallel pending assistants for the same conversation.
        pending = await session.scalar(
            select(Message.id).where(
                Message.conversation_id == conversation.id,
                Message.user_id == user.id,
                Message.role == MessageRole.assistant,
                Message.status == MessageStatus.pending,
                Message.is_active.is_(True),
            )
        )
        if pending is not None:
            from app.conversations.exceptions import ConversationConflictError

            raise ConversationConflictError()

        sequence = await self._next_sequence(session, conversation.id)
        message = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            user_id=user.id,
            role=MessageRole.assistant,
            content="",
            status=MessageStatus.pending,
            sequence_number=sequence,
            is_active=True,
            regenerated_from_message_id=regenerated_from_message_id,
        )
        session.add(message)
        await session.flush()
        await self.conversation_service.refresh_counters(session, conversation)
        return message

    async def finalize_assistant(
        self,
        session: AsyncSession,
        message: Message,
        *,
        content: str,
        grounded: bool | None,
        model: str | None,
        provider: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        latency_ms: float | None,
        finish_reason: str | None,
        citations: list[RagCitation] | None = None,
    ) -> Message:
        message.content = content
        message.status = MessageStatus.complete
        message.grounded = grounded
        message.model = model
        message.provider = provider
        message.prompt_tokens = prompt_tokens
        message.completion_tokens = completion_tokens
        message.total_tokens = total_tokens
        message.latency_ms = latency_ms
        message.finish_reason = finish_reason
        message.error_code = None
        message.updated_at = datetime.now(UTC)
        await session.flush()

        if citations:
            await self.persist_citations(session, message, citations)

        conversation = await session.scalar(
            select(Conversation).where(Conversation.id == message.conversation_id)
        )
        if conversation is not None:
            await self.conversation_service.refresh_counters(session, conversation)
        return (
            await session.scalar(
                select(Message)
                .where(Message.id == message.id)
                .options(selectinload(Message.citations))
            )
            or message
        )

    async def fail_assistant(
        self,
        session: AsyncSession,
        message: Message,
        *,
        error_code: str,
        content: str = "",
        partial_content: str | None = None,
    ) -> Message:
        message.status = MessageStatus.failed
        message.error_code = error_code
        message.content = partial_content if partial_content is not None else content
        message.updated_at = datetime.now(UTC)
        await session.flush()
        conversation = await session.scalar(
            select(Conversation).where(Conversation.id == message.conversation_id)
        )
        if conversation is not None:
            await self.conversation_service.refresh_counters(session, conversation)
        logger.info(
            "assistant_message_failed user_id=%s conversation_id=%s message_id=%s "
            "error_code=%s request_id=%s",
            message.user_id,
            message.conversation_id,
            message.id,
            error_code,
            request_id_ctx.get() or "-",
        )
        return message

    async def cancel_assistant(
        self,
        session: AsyncSession,
        message: Message,
        *,
        partial_content: str = "",
    ) -> Message:
        message.status = MessageStatus.cancelled
        message.content = partial_content
        message.error_code = "client_disconnected"
        message.updated_at = datetime.now(UTC)
        await session.flush()
        conversation = await session.scalar(
            select(Conversation).where(Conversation.id == message.conversation_id)
        )
        if conversation is not None:
            await self.conversation_service.refresh_counters(session, conversation)
        return message

    async def discard_empty_assistant(
        self,
        session: AsyncSession,
        message: Message,
    ) -> None:
        """Remove an unstarted cancelled assistant so no blank response persists."""
        if message.role != MessageRole.assistant or message.content.strip():
            return
        conversation = await session.scalar(
            select(Conversation).where(Conversation.id == message.conversation_id)
        )
        await session.delete(message)
        await session.flush()
        if conversation is not None:
            await self.conversation_service.refresh_counters(session, conversation)

    async def persist_citations(
        self,
        session: AsyncSession,
        message: Message,
        citations: list[RagCitation],
    ) -> list[MessageCitation]:
        excerpt_limit = self.settings.citation_excerpt_max_characters
        created: list[MessageCitation] = []
        for index, citation in enumerate(citations, start=1):
            excerpt = citation.excerpt.strip()
            if len(excerpt) > excerpt_limit:
                excerpt = excerpt[:excerpt_limit].rstrip() + "…"
            row = MessageCitation(
                id=uuid.uuid4(),
                message_id=message.id,
                conversation_id=message.conversation_id,
                user_id=message.user_id,
                document_id=citation.document_id,
                chunk_id=citation.chunk_id,
                citation_index=index,
                filename=citation.filename[:512],
                page_number=citation.page_number,
                chunk_index=citation.chunk_index,
                excerpt=excerpt,
                similarity_score=citation.similarity,
            )
            session.add(row)
            created.append(row)
        await session.flush()
        return created

    async def list_active_history(
        self,
        session: AsyncSession,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        before_sequence: int | None = None,
    ) -> list[Message]:
        filters = [
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
            Message.is_active.is_(True),
            Message.status == MessageStatus.complete,
            Message.role.in_([MessageRole.user, MessageRole.assistant]),
        ]
        if before_sequence is not None:
            filters.append(Message.sequence_number < before_sequence)
        rows = (
            await session.scalars(
                select(Message).where(*filters).order_by(Message.sequence_number.asc())
            )
        ).all()
        return list(rows)

    async def get_owned_message(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> Message:
        message = await session.scalar(
            select(Message)
            .options(selectinload(Message.citations))
            .where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
                Message.user_id == user.id,
            )
        )
        if message is None:
            raise MessageNotFoundError()
        return message

    async def edit_latest_user_message(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
        message_id: uuid.UUID,
        content: str,
    ) -> Message:
        cleaned = self._validate_content(content)
        target = await self.get_owned_message(session, user, conversation.id, message_id)
        if target.role != MessageRole.user or not target.is_active:
            raise MessageEditNotAllowedError()

        latest_user = await session.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.user_id == user.id,
                Message.role == MessageRole.user,
                Message.is_active.is_(True),
            )
            .order_by(Message.sequence_number.desc())
            .limit(1)
        )
        if latest_user is None or latest_user.id != target.id:
            raise MessageEditNotAllowedError("Only the latest user message can be edited")

        # Supersede following active assistant responses.
        following = (
            await session.scalars(
                select(Message).where(
                    Message.conversation_id == conversation.id,
                    Message.user_id == user.id,
                    Message.sequence_number > target.sequence_number,
                    Message.is_active.is_(True),
                )
            )
        ).all()
        for item in following:
            item.is_active = False
            item.updated_at = datetime.now(UTC)

        target.is_active = False
        target.updated_at = datetime.now(UTC)
        await session.flush()

        replacement = await self.append_user_message(
            session,
            user,
            conversation,
            cleaned,
            edited_from_message_id=target.id,
        )
        logger.info(
            "message_edited user_id=%s conversation_id=%s message_id=%s "
            "edited_from=%s request_id=%s",
            user.id,
            conversation.id,
            replacement.id,
            target.id,
            request_id_ctx.get() or "-",
        )
        return replacement

    async def prepare_regeneration(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
    ) -> tuple[Message, Message | None]:
        """Return (latest_user_message, previous_assistant_or_none)."""
        latest_user = await session.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.user_id == user.id,
                Message.role == MessageRole.user,
                Message.is_active.is_(True),
                Message.status == MessageStatus.complete,
            )
            .order_by(Message.sequence_number.desc())
            .limit(1)
        )
        if latest_user is None:
            raise MessageRegenerationNotAllowedError("No user message available to regenerate")

        latest_assistant = await session.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.user_id == user.id,
                Message.role == MessageRole.assistant,
                Message.is_active.is_(True),
                Message.sequence_number > latest_user.sequence_number,
            )
            .order_by(Message.sequence_number.desc())
            .limit(1)
        )
        if latest_assistant is not None:
            if latest_assistant.status == MessageStatus.pending:
                from app.conversations.exceptions import ConversationConflictError

                raise ConversationConflictError()
            latest_assistant.is_active = False
            latest_assistant.updated_at = datetime.now(UTC)
            await session.flush()

        return latest_user, latest_assistant
