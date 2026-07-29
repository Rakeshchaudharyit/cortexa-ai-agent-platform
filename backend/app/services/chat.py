"""Multi-turn conversational chat orchestration with RAG, streaming, titles, and summaries."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.conversations.context import ConversationContextBuilder
from app.conversations.exceptions import (
    DuplicateClientRequestError,
    GeneralChatDisabledError,
    MessageTooLargeError,
)
from app.conversations.schemas import (
    CreateMessageRequest,
    CreateMessageResponse,
    RegenerateRequest,
    UsageSummaryResponse,
)
from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.logging import request_id_ctx
from app.documents.schemas import RagCitation
from app.llm.schemas import (
    ChatMessage,
    GenerateRequest,
    StreamEvent,
    StreamEventType,
)
from app.llm.schemas import (
    MessageRole as LLMRole,
)
from app.models.conversation import DEFAULT_CONVERSATION_TITLE, Conversation, Message
from app.models.document import Document
from app.models.enums import ConversationStatus, MessageRole, MessageStatus
from app.models.user import User
from app.services.conversations import (
    ConversationService,
    conversation_to_summary,
    message_to_response,
)
from app.services.llm import LLMService
from app.services.messages import MessageService
from app.services.retrieval import RetrievalService, RetrievedChunk

logger = logging.getLogger("cortexa.chat")

_NO_CONTEXT_ANSWER = (
    "I could not find enough information in your uploaded documents to answer that question."
)

TitleGenerator = Callable[[str, str], Awaitable[str]]
Summarizer = Callable[[str | None, list[Message]], Awaitable[str]]


class ChatService:
    """Coordinate conversation messages, retrieval, generation, and metadata."""

    def __init__(
        self,
        settings: Settings,
        conversation_service: ConversationService,
        message_service: MessageService,
        retrieval_service: RetrievalService,
        llm_service: LLMService,
        context_builder: ConversationContextBuilder | None = None,
        *,
        title_generator: TitleGenerator | None = None,
        summarizer: Summarizer | None = None,
    ) -> None:
        self.settings = settings
        self.conversation_service = conversation_service
        self.message_service = message_service
        self.retrieval_service = retrieval_service
        self.llm_service = llm_service
        self.context_builder = context_builder or ConversationContextBuilder(settings)
        self.title_generator = title_generator
        self.summarizer = summarizer

    async def send_message(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        request: CreateMessageRequest,
    ) -> CreateMessageResponse:
        conversation = await self.conversation_service.require_active_conversation(
            session,
            user,
            conversation_id,
            for_update=True,
        )
        self._validate_content_length(request.content)

        replay = await self._idempotent_replay(
            session,
            user,
            conversation,
            request.client_request_id,
        )
        if replay is not None:
            return replay

        user_message = await self.message_service.append_user_message(
            session,
            user,
            conversation,
            request.content,
            client_request_id=request.client_request_id,
        )
        assistant = await self.message_service.create_pending_assistant(
            session,
            user,
            conversation,
        )
        await session.commit()

        try:
            await self._generate_into_assistant(
                session,
                user,
                conversation,
                user_message,
                assistant,
                document_ids=request.document_ids,
                top_k=request.top_k,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            await session.commit()
        except AppError:
            # Clean domain errors (validation, foreign doc, etc.) — no rollback needed
            # since we committed after creating user_message/assistant; let it propagate.
            raise
        except Exception:
            # Unexpected errors — best-effort fail marker.
            await session.rollback()
            await self._mark_failed(session, assistant.id, "generation_failed")
            raise

        return await self._build_create_response(session, conversation, user_message, assistant)

    async def stream_message(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        request: CreateMessageRequest,
    ) -> AsyncIterator[StreamEvent]:
        conversation = await self.conversation_service.require_active_conversation(
            session,
            user,
            conversation_id,
            for_update=True,
        )
        self._validate_content_length(request.content)

        if request.client_request_id is not None:
            existing = await self.message_service.find_by_client_request_id(
                session,
                user,
                conversation.id,
                request.client_request_id,
            )
            if existing is not None:
                assistant = await self._following_assistant(session, user, existing)
                if assistant is not None and assistant.status == MessageStatus.complete:
                    async for event in self._replay_stream(conversation, existing, assistant):
                        yield event
                    return
                raise DuplicateClientRequestError()

        user_message = await self.message_service.append_user_message(
            session,
            user,
            conversation,
            request.content,
            client_request_id=request.client_request_id,
        )
        assistant = await self.message_service.create_pending_assistant(
            session,
            user,
            conversation,
        )
        await session.commit()

        yield StreamEvent(
            event=StreamEventType.start,
            data={
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant.id),
            },
        )

        async for event in self._stream_into_assistant(
            session,
            user,
            conversation,
            user_message,
            assistant,
            document_ids=request.document_ids,
            top_k=request.top_k,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ):
            yield event

    async def regenerate(
        self,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID,
        request: RegenerateRequest,
    ) -> CreateMessageResponse:
        conversation = await self.conversation_service.require_active_conversation(
            session,
            user,
            conversation_id,
            for_update=True,
        )
        user_message, previous = await self.message_service.prepare_regeneration(
            session,
            user,
            conversation,
        )
        assistant = await self.message_service.create_pending_assistant(
            session,
            user,
            conversation,
            regenerated_from_message_id=previous.id if previous else None,
        )
        await session.commit()
        logger.info(
            "regeneration_started user_id=%s conversation_id=%s message_id=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            request_id_ctx.get() or "-",
        )
        try:
            await self._generate_into_assistant(
                session,
                user,
                conversation,
                user_message,
                assistant,
                document_ids=request.document_ids,
                top_k=request.top_k,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            await session.commit()
        except AppError:
            await session.rollback()
            await self._mark_failed(session, assistant.id, "generation_failed")
            raise
        except Exception:
            await session.rollback()
            await self._mark_failed(session, assistant.id, "generation_failed")
            raise

        return await self._build_create_response(session, conversation, user_message, assistant)

    async def usage_summary(self, session: AsyncSession, user: User) -> UsageSummaryResponse:
        conversations = int(
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == user.id)
            )
            or 0
        )
        active_conversations = int(
            await session.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(
                    Conversation.user_id == user.id,
                    Conversation.status == ConversationStatus.active,
                )
            )
            or 0
        )
        messages = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.user_id == user.id, Message.is_active.is_(True))
            )
            or 0
        )
        user_messages = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.user_id == user.id,
                    Message.is_active.is_(True),
                    Message.role == MessageRole.user,
                )
            )
            or 0
        )
        assistant_messages = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.user_id == user.id,
                    Message.is_active.is_(True),
                    Message.role == MessageRole.assistant,
                )
            )
            or 0
        )
        documents = int(
            await session.scalar(
                select(func.count()).select_from(Document).where(Document.user_id == user.id)
            )
            or 0
        )
        known_prompt = int(
            await session.scalar(
                select(func.coalesce(func.sum(Message.prompt_tokens), 0)).where(
                    Message.user_id == user.id,
                    Message.prompt_tokens.is_not(None),
                )
            )
            or 0
        )
        known_completion = int(
            await session.scalar(
                select(func.coalesce(func.sum(Message.completion_tokens), 0)).where(
                    Message.user_id == user.id,
                    Message.completion_tokens.is_not(None),
                )
            )
            or 0
        )
        known_total = int(
            await session.scalar(
                select(func.coalesce(func.sum(Message.total_tokens), 0)).where(
                    Message.user_id == user.id,
                    Message.total_tokens.is_not(None),
                )
            )
            or 0
        )
        average_latency = await session.scalar(
            select(func.avg(Message.latency_ms)).where(
                Message.user_id == user.id,
                Message.latency_ms.is_not(None),
            )
        )
        return UsageSummaryResponse(
            conversations=conversations,
            active_conversations=active_conversations,
            messages=messages,
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            documents=documents,
            known_prompt_tokens=known_prompt,
            known_completion_tokens=known_completion,
            known_total_tokens=known_total,
            average_latency_ms=round(float(average_latency), 2)
            if average_latency is not None
            else None,
        )

    def _validate_content_length(self, content: str) -> None:
        if len(content) > self.settings.message_max_characters:
            raise MessageTooLargeError()

    async def _mark_failed(
        self,
        session: AsyncSession,
        message_id: uuid.UUID,
        error_code: str,
    ) -> None:
        try:
            async with session.begin():
                fresh = await session.scalar(select(Message).where(Message.id == message_id))
                if fresh is not None and fresh.status == MessageStatus.pending:
                    await self.message_service.fail_assistant(session, fresh, error_code=error_code)
        except Exception:
            pass  # Best-effort; original error takes precedence.

    async def _following_assistant(
        self,
        session: AsyncSession,
        user: User,
        user_message: Message,
    ) -> Message | None:
        result = await session.scalar(
            select(Message)
            .options(selectinload(Message.citations))
            .where(
                Message.conversation_id == user_message.conversation_id,
                Message.user_id == user.id,
                Message.role == MessageRole.assistant,
                Message.sequence_number > user_message.sequence_number,
            )
            .order_by(Message.sequence_number.asc())
            .limit(1)
        )
        return result if isinstance(result, Message) else None

    async def _idempotent_replay(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
        client_request_id: uuid.UUID | None,
    ) -> CreateMessageResponse | None:
        if client_request_id is None:
            return None
        existing = await self.message_service.find_by_client_request_id(
            session,
            user,
            conversation.id,
            client_request_id,
        )
        if existing is None:
            return None
        assistant = await self._following_assistant(session, user, existing)
        if assistant is None:
            raise DuplicateClientRequestError()
        return await self._build_create_response(session, conversation, existing, assistant)

    async def _build_create_response(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: Message,
        assistant: Message,
    ) -> CreateMessageResponse:
        fresh_conv = (
            await session.scalar(select(Conversation).where(Conversation.id == conversation.id))
            or conversation
        )
        fresh_user = (
            await session.scalar(
                select(Message)
                .where(Message.id == user_message.id)
                .options(selectinload(Message.citations))
            )
            or user_message
        )
        fresh_asst = (
            await session.scalar(
                select(Message)
                .where(Message.id == assistant.id)
                .options(selectinload(Message.citations))
            )
            or assistant
        )
        return CreateMessageResponse(
            conversation=conversation_to_summary(fresh_conv),
            user_message=message_to_response(fresh_user),
            assistant_message=message_to_response(fresh_asst),
        )

    async def _replay_stream(
        self,
        conversation: Conversation,
        user_message: Message,
        assistant: Message,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            event=StreamEventType.start,
            data={
                "conversation_id": str(conversation.id),
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant.id),
            },
        )
        yield StreamEvent(
            event=StreamEventType.delta,
            data={"content": assistant.content},
        )
        response = message_to_response(assistant)
        for citation in response.citations:
            yield StreamEvent(
                event=StreamEventType.citation,
                data={"citation": citation.model_dump(mode="json")},
            )
        yield StreamEvent(
            event=StreamEventType.metadata,
            data={
                "model": assistant.model,
                "provider": assistant.provider,
                "prompt_tokens": assistant.prompt_tokens,
                "completion_tokens": assistant.completion_tokens,
                "total_tokens": assistant.total_tokens,
                "latency_ms": assistant.latency_ms,
            },
        )
        yield StreamEvent(
            event=StreamEventType.complete,
            data={"message": response.model_dump(mode="json")},
        )

    async def _resolve_retrieval(
        self,
        session: AsyncSession,
        user: User,
        *,
        query: str,
        document_ids: list[uuid.UUID] | None,
        top_k: int | None,
    ) -> tuple[list[RetrievedChunk], bool, bool]:
        """Return (retrieved, general_mode, retrieval_attempted).

        Policy:
        - document_ids is None → all owned ready documents (RAG)
        - document_ids == [] → no retrieval; general LLM chat if enabled
        - document_ids non-empty → selected documents only
        """
        if document_ids is not None and len(document_ids) == 0:
            if not self.settings.chat_general_mode_enabled:
                raise GeneralChatDisabledError()
            return [], True, False

        top = top_k if top_k is not None else self.settings.chat_default_top_k
        retrieved = await self.retrieval_service.retrieve(
            session,
            user,
            query=query,
            top_k=top,
            document_ids=document_ids,
        )
        return retrieved, False, True

    def _build_citations(self, retrieved: list[RetrievedChunk]) -> list[RagCitation]:
        excerpt_limit = self.settings.citation_excerpt_max_characters
        citations: list[RagCitation] = []
        for index, item in enumerate(retrieved, start=1):
            metadata = item.chunk.chunk_metadata or {}
            page_number = metadata.get("page_number")
            page_value = page_number if isinstance(page_number, int) else None
            excerpt = item.chunk.content.strip()
            if len(excerpt) > excerpt_limit:
                excerpt = excerpt[:excerpt_limit].rstrip() + "…"
            citations.append(
                RagCitation(
                    citation_id=f"[{index}]",
                    document_id=item.document.id,
                    filename=item.document.original_filename,
                    chunk_id=item.chunk.id,
                    chunk_index=item.chunk.chunk_index,
                    page_number=page_value,
                    excerpt=excerpt,
                    similarity=round(item.similarity, 6),
                )
            )
        return citations

    async def _generate_into_assistant(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
        user_message: Message,
        assistant: Message,
        *,
        document_ids: list[uuid.UUID] | None,
        top_k: int | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> Message:
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        logger.info(
            "generation_started user_id=%s conversation_id=%s message_id=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            request_id,
        )

        retrieved, general_mode, retrieval_attempted = await self._resolve_retrieval(
            session,
            user,
            query=user_message.content,
            document_ids=document_ids,
            top_k=top_k,
        )
        logger.info(
            "retrieval_count user_id=%s conversation_id=%s retrieval_count=%s "
            "general_mode=%s request_id=%s",
            user.id,
            conversation.id,
            len(retrieved),
            general_mode,
            request_id,
        )

        if retrieval_attempted and not retrieved:
            logger.info(
                "no_context_fallback user_id=%s conversation_id=%s request_id=%s",
                user.id,
                conversation.id,
                request_id,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            finalized = await self.message_service.finalize_assistant(
                session,
                assistant,
                content=_NO_CONTEXT_ANSWER,
                grounded=False,
                model=self.llm_service.provider.default_model,
                provider=self.llm_service.provider.name,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                latency_ms=latency_ms,
                finish_reason="no_context",
                citations=[],
            )
            await self._maybe_update_title(session, conversation, user_message, finalized)
            await self._maybe_update_summary(session, conversation, user)
            return finalized

        history = await self.message_service.list_active_history(
            session,
            conversation.id,
            user.id,
            before_sequence=user_message.sequence_number,
        )
        built = self.context_builder.build(
            current_user_content=user_message.content,
            history_messages=history,
            summary=conversation.summary,
            retrieved=retrieved,
            general_mode=general_mode,
        )
        if built.trimmed:
            logger.info(
                "context_trimming user_id=%s conversation_id=%s history_count=%s "
                "history_chars=%s rag_chars=%s included_summary=%s request_id=%s",
                user.id,
                conversation.id,
                built.history_message_count,
                built.history_character_count,
                built.rag_character_count,
                built.included_summary,
                request_id,
            )

        citations = self._build_citations(retrieved) if not general_mode else []
        generate_request = GenerateRequest(
            messages=built.messages,
            system=built.system,
            temperature=temperature
            if temperature is not None
            else self.settings.chat_default_temperature,
            max_tokens=max_tokens
            if max_tokens is not None
            else self.settings.message_max_response_tokens,
        )
        try:
            generation = await self.llm_service.generate(generate_request)
        except AppError as exc:
            await self.message_service.fail_assistant(
                session,
                assistant,
                error_code=exc.code,
            )
            logger.info(
                "generation_failed user_id=%s conversation_id=%s message_id=%s "
                "error_code=%s request_id=%s",
                user.id,
                conversation.id,
                assistant.id,
                exc.code,
                request_id,
            )
            raise

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        usage = generation.usage
        finalized = await self.message_service.finalize_assistant(
            session,
            assistant,
            content=generation.content,
            grounded=True if citations else (None if general_mode else False),
            model=generation.model,
            provider=generation.provider,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            latency_ms=latency_ms,
            finish_reason=generation.finish_reason,
            citations=citations,
        )
        logger.info(
            "generation_completed user_id=%s conversation_id=%s message_id=%s "
            "latency_ms=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            latency_ms,
            request_id,
        )
        await self._maybe_update_title(session, conversation, user_message, finalized)
        await self._maybe_update_summary(session, conversation, user)
        return finalized

    async def _stream_into_assistant(
        self,
        session: AsyncSession,
        user: User,
        conversation: Conversation,
        user_message: Message,
        assistant: Message,
        *,
        document_ids: list[uuid.UUID] | None,
        top_k: int | None,
        temperature: float | None,
        max_tokens: int | None,
    ) -> AsyncIterator[StreamEvent]:
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        logger.info(
            "stream_started user_id=%s conversation_id=%s message_id=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            request_id,
        )

        try:
            retrieved, general_mode, retrieval_attempted = await self._resolve_retrieval(
                session,
                user,
                query=user_message.content,
                document_ids=document_ids,
                top_k=top_k,
            )
        except AppError as exc:
            await self.message_service.fail_assistant(
                session,
                assistant,
                error_code=exc.code,
            )
            await session.commit()
            yield StreamEvent(
                event=StreamEventType.error,
                data={"error": {"code": exc.code, "message": exc.message}},
            )
            return

        logger.info(
            "retrieval_count user_id=%s conversation_id=%s retrieval_count=%s request_id=%s",
            user.id,
            conversation.id,
            len(retrieved),
            request_id,
        )

        if retrieval_attempted and not retrieved:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            finalized = await self.message_service.finalize_assistant(
                session,
                assistant,
                content=_NO_CONTEXT_ANSWER,
                grounded=False,
                model=self.llm_service.provider.default_model,
                provider=self.llm_service.provider.name,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                latency_ms=latency_ms,
                finish_reason="no_context",
                citations=[],
            )
            await self._maybe_update_title(session, conversation, user_message, finalized)
            await self._maybe_update_summary(session, conversation, user)
            await session.commit()
            finalized = (
                await session.scalar(
                    select(Message)
                    .where(Message.id == finalized.id)
                    .options(selectinload(Message.citations))
                )
                or finalized
            )
            yield StreamEvent(event=StreamEventType.delta, data={"content": _NO_CONTEXT_ANSWER})
            yield StreamEvent(
                event=StreamEventType.metadata,
                data={
                    "model": finalized.model,
                    "provider": finalized.provider,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "latency_ms": latency_ms,
                },
            )
            yield StreamEvent(
                event=StreamEventType.complete,
                data={"message": message_to_response(finalized).model_dump(mode="json")},
            )
            return

        history = await self.message_service.list_active_history(
            session,
            conversation.id,
            user.id,
            before_sequence=user_message.sequence_number,
        )
        built = self.context_builder.build(
            current_user_content=user_message.content,
            history_messages=history,
            summary=conversation.summary,
            retrieved=retrieved,
            general_mode=general_mode,
        )
        citations = self._build_citations(retrieved) if not general_mode else []
        for citation in citations:
            yield StreamEvent(
                event=StreamEventType.citation,
                data={"citation": citation.model_dump(mode="json")},
            )

        generate_request = GenerateRequest(
            messages=built.messages,
            system=built.system,
            temperature=temperature
            if temperature is not None
            else self.settings.chat_default_temperature,
            max_tokens=max_tokens
            if max_tokens is not None
            else self.settings.message_max_response_tokens,
        )

        accumulated = ""
        final_meta: dict[str, Any] = {}
        try:
            async for event in self.llm_service.stream(generate_request):
                if event.event == StreamEventType.delta:
                    chunk = str(event.data.get("content") or "")
                    accumulated += chunk
                    yield StreamEvent(event=StreamEventType.delta, data={"content": chunk})
                elif event.event == StreamEventType.complete:
                    final_meta = event.data
                    if not accumulated:
                        accumulated = str(event.data.get("content") or "")
                elif event.event == StreamEventType.error:
                    await self.message_service.fail_assistant(
                        session,
                        assistant,
                        error_code=str(event.data.get("code") or "stream_error"),
                        partial_content=accumulated,
                    )
                    await session.commit()
                    yield StreamEvent(
                        event=StreamEventType.error,
                        data={
                            "error": {
                                "code": event.data.get("code", "stream_error"),
                                "message": event.data.get("message", "Streaming failed"),
                            }
                        },
                    )
                    return
                elif event.event == StreamEventType.start:
                    continue
        except AppError as exc:
            await self.message_service.fail_assistant(
                session,
                assistant,
                error_code=exc.code,
                partial_content=accumulated,
            )
            await session.commit()
            yield StreamEvent(
                event=StreamEventType.error,
                data={"error": {"code": exc.code, "message": exc.message}},
            )
            return
        except Exception:
            await self.message_service.fail_assistant(
                session,
                assistant,
                error_code="stream_error",
                partial_content=accumulated,
            )
            await session.commit()
            logger.exception(
                "stream_unexpected_failure conversation_id=%s message_id=%s request_id=%s",
                conversation.id,
                assistant.id,
                request_id,
            )
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "error": {
                        "code": "conversation_stream_error",
                        "message": "Streaming generation failed",
                    }
                },
            )
            return

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        raw_usage = final_meta.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        finalized = await self.message_service.finalize_assistant(
            session,
            assistant,
            content=accumulated or str(final_meta.get("content") or ""),
            grounded=True if citations else (None if general_mode else False),
            model=str(final_meta.get("model") or self.llm_service.provider.default_model),
            provider=str(final_meta.get("provider") or self.llm_service.provider.name),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=latency_ms,
            finish_reason=final_meta.get("finish_reason"),
            citations=citations,
        )
        await self._maybe_update_title(session, conversation, user_message, finalized)
        await self._maybe_update_summary(session, conversation, user)
        await session.commit()
        finalized = (
            await session.scalar(
                select(Message)
                .where(Message.id == finalized.id)
                .options(selectinload(Message.citations))
            )
            or finalized
        )

        yield StreamEvent(
            event=StreamEventType.metadata,
            data={
                "model": finalized.model,
                "provider": finalized.provider,
                "prompt_tokens": finalized.prompt_tokens,
                "completion_tokens": finalized.completion_tokens,
                "total_tokens": finalized.total_tokens,
                "latency_ms": finalized.latency_ms,
            },
        )
        yield StreamEvent(
            event=StreamEventType.complete,
            data={"message": message_to_response(finalized).model_dump(mode="json")},
        )
        logger.info(
            "stream_completed user_id=%s conversation_id=%s message_id=%s "
            "latency_ms=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            latency_ms,
            request_id,
        )

    async def _maybe_update_title(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: Message,
        assistant: Message,
    ) -> None:
        if not self.settings.conversation_auto_title_enabled:
            return
        if not conversation.title_is_auto:
            return
        if conversation.title != DEFAULT_CONVERSATION_TITLE:
            return
        if assistant.status != MessageStatus.complete:
            return
        active_assistants = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.role == MessageRole.assistant,
                    Message.is_active.is_(True),
                    Message.status == MessageStatus.complete,
                )
            )
            or 0
        )
        if active_assistants != 1:
            return
        try:
            title = await self._generate_title(user_message.content, assistant.content)
            cleaned = self.conversation_service.sanitize_generated_title(title)
            conversation.title = cleaned
            conversation.title_is_auto = True
            conversation.updated_at = datetime.now(UTC)
            await session.flush()
            logger.info(
                "title_generation_success conversation_id=%s request_id=%s",
                conversation.id,
                request_id_ctx.get() or "-",
            )
        except Exception:
            logger.info(
                "title_generation_failure conversation_id=%s request_id=%s",
                conversation.id,
                request_id_ctx.get() or "-",
            )

    async def _generate_title(self, user_content: str, assistant_content: str) -> str:
        if self.title_generator is not None:
            return await self.title_generator(user_content, assistant_content)
        snippet_user = user_content.strip()[:240]
        snippet_assistant = assistant_content.strip()[:240]
        result = await self.llm_service.generate(
            GenerateRequest(
                messages=[
                    ChatMessage(
                        role=LLMRole.user,
                        content=(
                            "Create a short conversation title (max 8 words). "
                            "Return only the title text.\n\n"
                            f"User: {snippet_user}\nAssistant: {snippet_assistant}"
                        ),
                    )
                ],
                temperature=0.2,
                max_tokens=24,
            )
        )
        return result.content

    async def _maybe_update_summary(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user: User,
    ) -> None:
        if not self.settings.conversation_summary_enabled:
            return
        active_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.user_id == user.id,
                    Message.is_active.is_(True),
                    Message.status == MessageStatus.complete,
                    Message.role.in_([MessageRole.user, MessageRole.assistant]),
                )
            )
            or 0
        )
        if active_count < self.settings.conversation_summary_trigger_messages:
            return

        keep = self.settings.conversation_max_history_messages
        history = await self.message_service.list_active_history(
            session,
            conversation.id,
            user.id,
        )
        if len(history) <= keep:
            return
        older = history[:-keep]
        logger.info(
            "summary_triggered conversation_id=%s older_count=%s request_id=%s",
            conversation.id,
            len(older),
            request_id_ctx.get() or "-",
        )
        try:
            summary = await self._generate_summary(conversation.summary, older)
            max_chars = self.settings.conversation_summary_max_characters
            if len(summary) > max_chars:
                summary = summary[:max_chars].rstrip()
            conversation.summary = summary
            conversation.summary_updated_at = datetime.now(UTC)
            conversation.updated_at = datetime.now(UTC)
            await session.flush()
            logger.info(
                "summary_success conversation_id=%s request_id=%s",
                conversation.id,
                request_id_ctx.get() or "-",
            )
        except Exception:
            logger.info(
                "summary_failure conversation_id=%s request_id=%s",
                conversation.id,
                request_id_ctx.get() or "-",
            )

    async def _generate_summary(
        self,
        existing: str | None,
        older_messages: list[Message],
    ) -> str:
        if self.summarizer is not None:
            return await self.summarizer(existing, older_messages)
        lines: list[str] = []
        for message in older_messages[-40:]:
            snippet = message.content.strip()
            if len(snippet) > 400:
                snippet = snippet[:400] + "…"
            lines.append(f"{message.role.value}: {snippet}")
        prior = (existing or "").strip()
        prompt = (
            "Summarize this conversation segment for later context. "
            "Be factual and concise. Do not invent details.\n\n"
        )
        if prior:
            prompt += f"Existing summary:\n{prior}\n\n"
        prompt += "Messages:\n" + "\n".join(lines)
        result = await self.llm_service.generate(
            GenerateRequest(
                messages=[ChatMessage(role=LLMRole.user, content=prompt)],
                temperature=0.2,
                max_tokens=400,
            )
        )
        return result.content.strip()
