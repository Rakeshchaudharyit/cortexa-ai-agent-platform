"""Multi-turn conversational chat orchestration with RAG, streaming, titles, and summaries."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import AgentOrchestrator
from app.agents.schemas import AgentRunConfig
from app.agents.tool_selection import (
    ToolSelectionContext,
    ToolSelectionResult,
    resolve_conversation_mode,
    select_tools_for_turn,
)
from app.conversations.citations import (
    dedupe_retrieved_chunks,
    normalize_grounded_answer,
    rag_citation_to_response,
)
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
from app.memory.chat_integration import maybe_extract_after_turn, prepare_memory_for_turn
from app.memory.extractor import MemoryExtractor
from app.memory.retrieval import MemoryRetriever
from app.memory.service import MemoryService
from app.models.conversation import DEFAULT_CONVERSATION_TITLE, Conversation, Message
from app.models.document import Document
from app.models.enums import ConversationStatus, DocumentStatus, MessageRole, MessageStatus
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
    "I couldn’t find that information in the selected documents. "
    "Try choosing different documents or switch to General Agent mode."
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
        agent_orchestrator: AgentOrchestrator | None = None,
        memory_service: MemoryService | None = None,
        memory_retriever: MemoryRetriever | None = None,
        memory_extractor: MemoryExtractor | None = None,
        multi_agent_service: Any | None = None,
    ) -> None:
        self.settings = settings
        self.conversation_service = conversation_service
        self.message_service = message_service
        self.retrieval_service = retrieval_service
        self.llm_service = llm_service
        self.context_builder = context_builder or ConversationContextBuilder(settings)
        self.title_generator = title_generator
        self.summarizer = summarizer
        self.agent_orchestrator = agent_orchestrator
        self.memory_service = memory_service
        self.memory_retriever = memory_retriever
        self.memory_extractor = memory_extractor
        self.multi_agent_service = multi_agent_service

    @property
    def tools_enabled(self) -> bool:
        return bool(self.settings.agent_tools_enabled and self.agent_orchestrator is not None)

    @property
    def multi_agent_enabled(self) -> bool:
        return bool(self.settings.multi_agent_enabled and self.multi_agent_service is not None)

    async def classify_complexity(
        self,
        *,
        user_message: str,
        conversation_mode: str = "general",
        selected_document_ids: list[uuid.UUID] | None = None,
        memory_enabled: bool = False,
        explicit_memory_intent: bool = False,
        selected_tool_intent: list[str] | None = None,
        conversation_context_summary: str | None = None,
    ) -> Any | None:
        """Feature-gated complexity classification (Phase 9.2 internal)."""
        if not self.multi_agent_enabled or self.multi_agent_service is None:
            return None
        return await self.multi_agent_service.classify(
            user_message=user_message,
            conversation_mode=conversation_mode,
            selected_document_ids=selected_document_ids,
            memory_enabled=memory_enabled,
            explicit_memory_intent=explicit_memory_intent,
            selected_tool_intent=selected_tool_intent,
            conversation_context_summary=conversation_context_summary,
        )

    async def _select_tools_for_turn(
        self,
        *,
        session: AsyncSession,
        user: User,
        user_content: str,
        document_ids: list[uuid.UUID] | None,
        memory_enabled: bool,
        has_accessible_documents: bool | None = None,
    ) -> ToolSelectionResult:
        """Deterministic tool allow-list for this turn (never client-controlled)."""
        if not self.tools_enabled or self.agent_orchestrator is None:
            return ToolSelectionResult(selected_tool_names=[], reason_codes=["tools_disabled"])

        mode = resolve_conversation_mode(document_ids)
        if has_accessible_documents is None:
            if mode == "general":
                has_docs = False
            elif document_ids:
                has_docs = True
            else:
                count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(
                            Document.user_id == user.id,
                            Document.status == DocumentStatus.ready,
                        )
                    )
                    or 0
                )
                has_docs = count > 0
        else:
            has_docs = has_accessible_documents

        registered = frozenset(
            tool.name for tool in self.agent_orchestrator.tool_registry.list_enabled(role=user.role)
        )
        global_memory = bool(self.settings.memory_enabled)
        return select_tools_for_turn(
            ToolSelectionContext(
                user_message=user_content,
                conversation_mode=mode,
                document_ids=document_ids,
                has_accessible_documents=has_docs,
                memory_globally_enabled=global_memory,
                conversation_memory_enabled=memory_enabled,
                registered_tool_names=registered,
            )
        )

    def _agent_run_config(
        self,
        *,
        selection: ToolSelectionResult,
        temperature: float | None,
        max_tokens: int | None,
        conversation_mode: str,
        memory_context_count: int,
        rag_context_count: int,
    ) -> AgentRunConfig:
        return AgentRunConfig(
            max_iterations=self.settings.agent_max_tool_iterations,
            temperature=temperature,
            max_tokens=max_tokens,
            selected_tool_names=list(selection.selected_tool_names),
            selection_reason_codes=list(selection.reason_codes),
            conversation_mode=conversation_mode,
            memory_context_count=memory_context_count,
            rag_context_count=rag_context_count,
        )

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
            client_request_id=request.client_request_id,
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
        agent_run_id = (assistant.message_metadata or {}).get("agent_run_id")
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
                **({"agent_run_id": agent_run_id} if agent_run_id else {}),
            },
        )
        yield StreamEvent(
            event=StreamEventType.complete,
            data={
                "message": response.model_dump(mode="json"),
                **({"agent_run_id": agent_run_id} if agent_run_id else {}),
            },
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
        for index, item in enumerate(dedupe_retrieved_chunks(retrieved), start=1):
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

    def _citation_sse_payloads(self, citations: list[RagCitation]) -> list[dict[str, Any]]:
        """Serialize citations for SSE using the same schema as persisted messages."""
        return [
            rag_citation_to_response(citation, index=index).model_dump(mode="json")
            for index, citation in enumerate(citations, start=1)
        ]

    @staticmethod
    def _progress_event(
        phase: str,
        message: str,
        **extra: Any,
    ) -> StreamEvent:
        data: dict[str, Any] = {"phase": phase, "message": message}
        data.update(extra)
        return StreamEvent(event=StreamEventType.progress, data=data)

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
        retrieved = dedupe_retrieved_chunks(retrieved)
        logger.info(
            "retrieval_count user_id=%s conversation_id=%s retrieval_count=%s "
            "general_mode=%s request_id=%s",
            user.id,
            conversation.id,
            len(retrieved),
            general_mode,
            request_id,
        )

        memory_turn = await prepare_memory_for_turn(
            session=session,
            user=user,
            conversation=conversation,
            user_content=user_message.content,
            user_message_id=user_message.id,
            memory_service=self.memory_service,
            memory_retriever=self.memory_retriever,
        )
        if memory_turn.short_circuit_reply:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            finalized = await self.message_service.finalize_assistant(
                session,
                assistant,
                content=memory_turn.short_circuit_reply,
                grounded=None,
                model=self.llm_service.provider.default_model,
                provider=self.llm_service.provider.name,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                latency_ms=latency_ms,
                finish_reason="memory_action",
                citations=[],
            )
            await self._maybe_update_title(session, conversation, user_message, finalized)
            await self._maybe_update_summary(session, conversation, user)
            return finalized

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
            memory_context=memory_turn.memory_context or None,
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

        if self.tools_enabled:
            assert self.agent_orchestrator is not None
            selection = await self._select_tools_for_turn(
                session=session,
                user=user,
                user_content=user_message.content,
                document_ids=document_ids,
                memory_enabled=memory_turn.memory_enabled,
                has_accessible_documents=None,
            )
            if retrieved and "knowledge_search" in selection.selected_tool_names:
                selection = ToolSelectionResult(
                    selected_tool_names=[
                        name for name in selection.selected_tool_names if name != "knowledge_search"
                    ],
                    reason_codes=[
                        *selection.reason_codes,
                        "knowledge_search_skipped_rag_preloaded",
                    ],
                )
            try:
                agent_result = await self.agent_orchestrator.run(
                    session=session,
                    user=user,
                    messages=built.messages,
                    system=built.system,
                    conversation_id=conversation.id,
                    message_id=assistant.id,
                    allowed_document_ids=document_ids,
                    config=self._agent_run_config(
                        selection=selection,
                        temperature=generate_request.temperature,
                        max_tokens=generate_request.max_tokens,
                        conversation_mode=resolve_conversation_mode(document_ids),
                        memory_context_count=len(memory_turn.retrieved),
                        rag_context_count=len(retrieved),
                    ),
                )
            except AppError as exc:
                await self.message_service.fail_assistant(
                    session,
                    assistant,
                    error_code=exc.code,
                )
                raise
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            meta = {
                "tool_execution_ids": agent_result.tool_execution_ids,
                "agent_iterations": agent_result.iterations,
                "memory_count": len(memory_turn.retrieved),
            }
            assistant.message_metadata = {
                **(assistant.message_metadata or {}),
                **meta,
            }
            answer_content = agent_result.content
            if not general_mode and citations:
                answer_content = normalize_grounded_answer(answer_content)
            finalized = await self.message_service.finalize_assistant(
                session,
                assistant,
                content=answer_content,
                grounded=True if citations else (None if general_mode else False),
                model=agent_result.model or self.llm_service.provider.default_model,
                provider=agent_result.provider or self.llm_service.provider.name,
                prompt_tokens=agent_result.prompt_tokens,
                completion_tokens=agent_result.completion_tokens,
                total_tokens=agent_result.total_tokens,
                latency_ms=latency_ms,
                finish_reason=agent_result.finish_reason,
                citations=citations,
            )
            logger.info(
                "generation_completed user_id=%s conversation_id=%s message_id=%s "
                "latency_ms=%s tools=%s request_id=%s",
                user.id,
                conversation.id,
                assistant.id,
                latency_ms,
                len(agent_result.tool_execution_ids),
                request_id,
            )
            await maybe_extract_after_turn(
                session=session,
                user=user,
                conversation=conversation,
                user_content=user_message.content,
                assistant_content=finalized.content,
                user_message_id=user_message.id,
                memory_service=self.memory_service,
                memory_extractor=self.memory_extractor,
            )
            await self._maybe_update_title(session, conversation, user_message, finalized)
            await self._maybe_update_summary(session, conversation, user)
            return finalized

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
        answer_content = generation.content
        if not general_mode and citations:
            answer_content = normalize_grounded_answer(answer_content)
        finalized = await self.message_service.finalize_assistant(
            session,
            assistant,
            content=answer_content,
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
        await maybe_extract_after_turn(
            session=session,
            user=user,
            conversation=conversation,
            user_content=user_message.content,
            assistant_content=finalized.content,
            user_message_id=user_message.id,
            memory_service=self.memory_service,
            memory_extractor=self.memory_extractor,
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
        client_request_id: uuid.UUID | None = None,
    ) -> AsyncIterator[StreamEvent]:
        request_id = request_id_ctx.get() or "-"
        started = time.perf_counter()
        timing: dict[str, Any] = {
            "embedding_ms": None,
            "retrieval_ms": None,
            "context_build_ms": None,
            "model_time_to_first_token_ms": None,
            "model_total_ms": None,
            "citation_build_ms": None,
            "total_request_ms": None,
            "retrieved_chunk_count": 0,
            "citation_count": 0,
            "provider_streaming": None,
        }
        logger.info(
            "stream_started user_id=%s conversation_id=%s message_id=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            request_id,
        )
        yield self._progress_event(
            "preparing",
            "Preparing your question…",
        )

        try:
            if document_ids is not None and len(document_ids) == 0:
                # General mode — skip retrieval progress.
                pass
            else:
                yield self._progress_event(
                    "retrieving",
                    "Searching selected documents…",
                )
            retrieval_started = time.perf_counter()
            retrieved, general_mode, retrieval_attempted = await self._resolve_retrieval(
                session,
                user,
                query=user_message.content,
                document_ids=document_ids,
                top_k=top_k,
            )
            timing["retrieval_ms"] = round((time.perf_counter() - retrieval_started) * 1000, 2)
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

        retrieved = dedupe_retrieved_chunks(retrieved)
        timing["retrieved_chunk_count"] = len(retrieved)
        logger.info(
            "retrieval_count user_id=%s conversation_id=%s retrieval_count=%s "
            "retrieval_ms=%s request_id=%s",
            user.id,
            conversation.id,
            len(retrieved),
            timing["retrieval_ms"],
            request_id,
        )
        if retrieval_attempted:
            if retrieved:
                yield self._progress_event(
                    "retrieval_complete",
                    f"Found {len(retrieved)} relevant "
                    f"{'passage' if len(retrieved) == 1 else 'passages'}",
                    retrieved_chunk_count=len(retrieved),
                )
            else:
                yield self._progress_event(
                    "retrieval_complete",
                    "No relevant passages found",
                    retrieved_chunk_count=0,
                )

        preliminary_decision = None
        if self.multi_agent_enabled and self.multi_agent_service is not None:
            preliminary_decision = await self.multi_agent_service.classify(
                user_message=user_message.content,
                conversation_mode=resolve_conversation_mode(document_ids),
                selected_document_ids=document_ids,
                memory_enabled=bool(conversation.memory_enabled_override is not False),
                conversation_context_summary=conversation.summary,
            )
        defer_persistent_writes = bool(
            preliminary_decision is not None
            and self.multi_agent_service is not None
            and self.multi_agent_service.should_use_multi_agent(preliminary_decision)
        )
        memory_turn = await prepare_memory_for_turn(
            session=session,
            user=user,
            conversation=conversation,
            user_content=user_message.content,
            user_message_id=user_message.id,
            memory_service=self.memory_service,
            memory_retriever=self.memory_retriever,
            defer_persistent_writes=defer_persistent_writes,
        )
        for event in memory_turn.events:
            yield event

        if memory_turn.short_circuit_reply:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            reply = memory_turn.short_circuit_reply
            finalized = await self.message_service.finalize_assistant(
                session,
                assistant,
                content=reply,
                grounded=None,
                model=self.llm_service.provider.default_model,
                provider=self.llm_service.provider.name,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                latency_ms=latency_ms,
                finish_reason="memory_action",
                citations=[],
            )
            await self._maybe_update_title(session, conversation, user_message, finalized)
            await self._maybe_update_summary(session, conversation, user)
            await session.commit()
            yield StreamEvent(event=StreamEventType.delta, data={"content": reply})
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
        context_started = time.perf_counter()
        built = self.context_builder.build(
            current_user_content=user_message.content,
            history_messages=history,
            summary=conversation.summary,
            retrieved=retrieved,
            general_mode=general_mode,
            memory_context=memory_turn.memory_context or None,
        )
        timing["context_build_ms"] = round((time.perf_counter() - context_started) * 1000, 2)
        citation_started = time.perf_counter()
        citations = self._build_citations(retrieved) if not general_mode else []
        timing["citation_build_ms"] = round((time.perf_counter() - citation_started) * 1000, 2)
        timing["citation_count"] = len(citations)
        if citations:
            yield self._progress_event(
                "citations",
                "Finalizing citations…",
                citation_count=len(citations),
            )
        for citation_payload in self._citation_sse_payloads(citations):
            yield StreamEvent(
                event=StreamEventType.citation,
                data={"citation": citation_payload},
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

        # Phase 9.3: classify before entering the existing streaming agent path.
        # Simple requests continue below unchanged and retain provider token streaming.
        if self.multi_agent_enabled and self.multi_agent_service is not None:
            conversation_mode = resolve_conversation_mode(document_ids)
            selection = await self._select_tools_for_turn(
                session=session,
                user=user,
                user_content=user_message.content,
                document_ids=document_ids,
                memory_enabled=memory_turn.memory_enabled,
                has_accessible_documents=bool(retrieved),
            )
            decision = preliminary_decision or await self.multi_agent_service.classify(
                user_message=user_message.content,
                conversation_mode=conversation_mode,
                selected_document_ids=document_ids,
                memory_enabled=memory_turn.memory_enabled,
                selected_tool_intent=selection.selected_tool_names,
                conversation_context_summary=conversation.summary,
            )
            if self.multi_agent_service.should_use_multi_agent(decision):
                from app.agents.api import safe_metadata

                history_payload = [
                    {"role": item.role.value, "content": item.content[:2000]}
                    for item in history[-self.settings.conversation_max_history_messages :]
                ]
                event_queue: asyncio.Queue[StreamEvent] = asyncio.Queue()

                async def on_agent_event(
                    run_id: uuid.UUID,
                    event_type: str,
                    agent_key: str | None,
                    task_id: uuid.UUID | None,
                    metadata: dict[str, object],
                ) -> None:
                    # Checkpoint state before exposing it. This makes the run
                    # visible to the owner-only cancel API while it is active.
                    await session.commit()
                    try:
                        stream_type = StreamEventType(event_type)
                    except ValueError:
                        return
                    clean = safe_metadata(metadata)
                    await event_queue.put(
                        StreamEvent(
                            event=stream_type,
                            data={
                                "agent_run_id": str(run_id),
                                "agent_key": agent_key,
                                "task_id": str(task_id) if task_id else None,
                                **(clean if isinstance(clean, dict) else {}),
                            },
                        )
                    )

                execution_task = asyncio.create_task(
                    self.multi_agent_service.execute(
                        session,
                        user=user,
                        user_message=user_message.content,
                        conversation_id=conversation.id,
                        conversation_mode=conversation_mode,
                        selected_document_ids=document_ids,
                        memory_enabled=memory_turn.memory_enabled,
                        selected_tool_intent=selection.selected_tool_names,
                        conversation_summary=conversation.summary,
                        selected_history=history_payload,
                        memory_context=[
                            item.model_dump(mode="json") for item in memory_turn.retrieved
                        ],
                        document_context=[],
                        correlation_id=str(client_request_id or assistant.id),
                        enabled_tool_names=frozenset(selection.selected_tool_names),
                        event_callback=on_agent_event,
                    ),
                    name=f"multi-agent-run-{assistant.id}",
                )
                try:
                    while not execution_task.done() or not event_queue.empty():
                        if not event_queue.empty():
                            yield event_queue.get_nowait()
                            continue
                        next_event = asyncio.create_task(event_queue.get())
                        done, _pending = await asyncio.wait(
                            {execution_task, next_event},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if next_event in done:
                            yield next_event.result()
                        else:
                            next_event.cancel()
                            try:
                                await next_event
                            except asyncio.CancelledError:
                                pass
                    result = await execution_task
                except asyncio.CancelledError:
                    execution_task.cancel()
                    try:
                        await execution_task
                    except asyncio.CancelledError:
                        pass
                    await session.rollback()
                    if not assistant.content.strip():
                        await self.message_service.discard_empty_assistant(session, assistant)
                    await session.commit()
                    raise
                await session.commit()
                if result.run is None:
                    await self.message_service.fail_assistant(
                        session, assistant, error_code="agent_run_missing"
                    )
                    await session.commit()
                    yield StreamEvent(
                        event=StreamEventType.error,
                        data={
                            "error": {
                                "code": "agent_run_missing",
                                "message": "Multi-agent execution failed",
                            }
                        },
                    )
                    return
                if result.error_code:
                    await self.message_service.fail_assistant(
                        session, assistant, error_code=result.error_code
                    )
                    await session.commit()
                    yield StreamEvent(
                        event=StreamEventType.error,
                        data={
                            "agent_run_id": str(result.run.id),
                            "error": {
                                "code": result.error_code,
                                "message": result.safe_error_message
                                or "Multi-agent execution failed",
                            },
                        },
                    )
                    return
                content = result.final_content.strip()
                if result.approval_required and not content:
                    content = (
                        "Your approval is required before I can complete " "the requested action."
                    )
                if not content:
                    await self.message_service.fail_assistant(
                        session, assistant, error_code="empty_assistant_response"
                    )
                    await session.commit()
                    yield StreamEvent(
                        event=StreamEventType.error,
                        data={
                            "agent_run_id": str(result.run.id),
                            "error": {
                                "code": "empty_assistant_response",
                                "message": "The agents returned an empty response",
                            },
                        },
                    )
                    return
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                assistant.message_metadata = {
                    **(assistant.message_metadata or {}),
                    "agent_run_id": str(result.run.id),
                    "execution_mode": "multi_agent",
                }
                finalized = await self.message_service.finalize_assistant(
                    session,
                    assistant,
                    content=content,
                    grounded=True if citations else (None if general_mode else False),
                    model=self.llm_service.provider.default_model,
                    provider=self.llm_service.provider.name,
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                    latency_ms=latency_ms,
                    finish_reason=("approval_required" if result.approval_required else "stop"),
                    citations=citations,
                )
                await session.commit()
                yield StreamEvent(event=StreamEventType.delta, data={"content": content})
                yield StreamEvent(
                    event=StreamEventType.metadata,
                    data={
                        "agent_run_id": str(result.run.id),
                        "execution_mode": "multi_agent",
                        "approval_required": result.approval_required,
                        "latency_ms": latency_ms,
                    },
                )
                yield StreamEvent(
                    event=StreamEventType.complete,
                    data={
                        "agent_run_id": str(result.run.id),
                        "message": message_to_response(finalized).model_dump(mode="json"),
                    },
                )
                return

        if not general_mode and retrieved:
            yield self._progress_event(
                "generating",
                "Generating grounded answer…",
            )
            yield self._progress_event(
                "generating_slow",
                "The local model is preparing a grounded answer…",
            )
        else:
            yield self._progress_event(
                "generating",
                "Generating response…",
            )

        if self.tools_enabled:
            assert self.agent_orchestrator is not None
            accumulated = ""
            agent_meta: dict[str, Any] = {}
            tool_execution_ids: list[str] = []
            cancelled = False
            stream_finished = False
            selection = await self._select_tools_for_turn(
                session=session,
                user=user,
                user_content=user_message.content,
                document_ids=document_ids,
                memory_enabled=memory_turn.memory_enabled,
                has_accessible_documents=None,
            )
            # ChatService already injected retrieved context + citations. Avoid a
            # second knowledge_search round-trip (extra latency + buffered generate).
            if retrieved and "knowledge_search" in selection.selected_tool_names:
                selection = ToolSelectionResult(
                    selected_tool_names=[
                        name for name in selection.selected_tool_names if name != "knowledge_search"
                    ],
                    reason_codes=[
                        *selection.reason_codes,
                        "knowledge_search_skipped_rag_preloaded",
                    ],
                )
            logger.info(
                "tool_selection conversation_id=%s tools_selected_count=%s "
                "selected_tool_names=%s reason_codes=%s conversation_mode=%s "
                "request_id=%s",
                conversation.id,
                selection.tools_selected_count,
                selection.selected_tool_names,
                selection.reason_codes,
                resolve_conversation_mode(document_ids),
                request_id,
            )
            model_started = time.perf_counter()
            first_token_at: float | None = None
            try:
                async for event in self.agent_orchestrator.stream(
                    session=session,
                    user=user,
                    messages=built.messages,
                    system=built.system,
                    conversation_id=conversation.id,
                    message_id=assistant.id,
                    allowed_document_ids=document_ids,
                    config=self._agent_run_config(
                        selection=selection,
                        temperature=generate_request.temperature,
                        max_tokens=generate_request.max_tokens,
                        conversation_mode=resolve_conversation_mode(document_ids),
                        memory_context_count=len(memory_turn.retrieved),
                        rag_context_count=len(retrieved),
                    ),
                ):
                    if event.event == StreamEventType.delta:
                        chunk = str(event.data.get("content") or "")
                        if chunk and first_token_at is None:
                            first_token_at = time.perf_counter()
                            timing["model_time_to_first_token_ms"] = round(
                                (first_token_at - model_started) * 1000, 2
                            )
                        accumulated += chunk
                        # Canonical text event only — never re-emit assistant_token.
                        yield event
                    elif event.event == StreamEventType.assistant_token:
                        # Legacy alias: do not forward duplicate text to clients.
                        continue
                    elif event.event == StreamEventType.agent_completed:
                        agent_meta = event.data
                        tool_execution_ids = [
                            str(x) for x in (event.data.get("tool_execution_ids") or [])
                        ]
                        timing["provider_streaming"] = event.data.get("provider_streaming")
                        if timing["model_time_to_first_token_ms"] is None:
                            timing["model_time_to_first_token_ms"] = event.data.get(
                                "time_to_first_token_ms"
                            )
                        timing["model_total_ms"] = event.data.get("total_generation_ms")
                        yield event
                    elif event.event in {
                        StreamEventType.agent_failed,
                        StreamEventType.error,
                    }:
                        err = event.data.get("error") or {}
                        if not isinstance(err, dict):
                            err = {}
                        code = str(err.get("code") or event.data.get("code") or "agent_failed")
                        message = str(
                            err.get("message")
                            or event.data.get("message")
                            or "Agent generation failed"
                        )
                        if code == "client_disconnected":
                            cancelled = True
                            await self.message_service.cancel_assistant(
                                session,
                                assistant,
                                partial_content=accumulated.strip(),
                            )
                            await session.commit()
                            stream_finished = True
                            yield StreamEvent(
                                event=StreamEventType.error,
                                data={"error": {"code": code, "message": message}},
                            )
                            return
                        await self.message_service.fail_assistant(
                            session,
                            assistant,
                            error_code=code,
                            partial_content=accumulated,
                        )
                        await session.commit()
                        stream_finished = True
                        yield StreamEvent(
                            event=StreamEventType.error,
                            data={"error": {"code": code, "message": message}},
                        )
                        return
                    else:
                        yield event
                stream_finished = True
                if timing["model_total_ms"] is None:
                    timing["model_total_ms"] = round(
                        (time.perf_counter() - model_started) * 1000, 2
                    )
            except asyncio.CancelledError:
                cancelled = True
                await self.message_service.cancel_assistant(
                    session,
                    assistant,
                    partial_content=accumulated.strip(),
                )
                await session.commit()
                stream_finished = True
                logger.info(
                    "stream_cancelled conversation_id=%s message_id=%s "
                    "partial_chars=%s request_id=%s",
                    conversation.id,
                    assistant.id,
                    len(accumulated.strip()),
                    request_id,
                )
                yield StreamEvent(
                    event=StreamEventType.error,
                    data={
                        "error": {
                            "code": "client_disconnected",
                            "message": "Generation cancelled",
                        }
                    },
                )
                return
            except AppError as exc:
                await self.message_service.fail_assistant(
                    session,
                    assistant,
                    error_code=exc.code,
                    partial_content=accumulated,
                )
                await session.commit()
                stream_finished = True
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
                stream_finished = True
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
            finally:
                if (
                    not stream_finished
                    and not cancelled
                    and assistant.status == MessageStatus.pending
                ):
                    # Generator closed by client disconnect (GeneratorExit) mid-stream.
                    await self.message_service.cancel_assistant(
                        session,
                        assistant,
                        partial_content=accumulated.strip(),
                    )
                    await session.commit()
                    cancelled = True
                    logger.info(
                        "stream_generator_closed conversation_id=%s message_id=%s "
                        "partial_chars=%s request_id=%s",
                        conversation.id,
                        assistant.id,
                        len(accumulated.strip()),
                        request_id,
                    )

            if cancelled:
                return

            # Do not persist a blank completed assistant message.
            if not accumulated.strip():
                await self.message_service.fail_assistant(
                    session,
                    assistant,
                    error_code="empty_assistant_response",
                    partial_content="",
                )
                await session.commit()
                yield StreamEvent(
                    event=StreamEventType.error,
                    data={
                        "error": {
                            "code": "empty_assistant_response",
                            "message": "The model returned an empty response",
                        }
                    },
                )
                return

            if not general_mode and citations:
                accumulated = normalize_grounded_answer(accumulated)

            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            timing["total_request_ms"] = latency_ms
            agent_usage = agent_meta.get("usage") or {}
            assistant.message_metadata = {
                **(assistant.message_metadata or {}),
                "tool_execution_ids": tool_execution_ids,
                "agent_iterations": agent_meta.get("iterations"),
                "tools_selected_count": selection.tools_selected_count,
                "selected_tool_names": selection.selected_tool_names,
                "rag_timing": {
                    k: timing[k]
                    for k in (
                        "embedding_ms",
                        "retrieval_ms",
                        "context_build_ms",
                        "model_time_to_first_token_ms",
                        "model_total_ms",
                        "citation_build_ms",
                        "total_request_ms",
                        "retrieved_chunk_count",
                        "citation_count",
                        "provider_streaming",
                    )
                },
            }
            finalized = await self.message_service.finalize_assistant(
                session,
                assistant,
                content=accumulated,
                grounded=True if citations else (None if general_mode else False),
                model=str(agent_meta.get("model") or self.llm_service.provider.default_model),
                provider=str(agent_meta.get("provider") or self.llm_service.provider.name),
                prompt_tokens=agent_usage.get("prompt_tokens"),
                completion_tokens=agent_usage.get("completion_tokens"),
                total_tokens=agent_usage.get("total_tokens"),
                latency_ms=latency_ms,
                finish_reason=str(agent_meta.get("finish_reason") or "stop"),
                citations=citations,
            )
            # Persist answer before slow post-processing so clients can clear Stop.
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
                    "latency_ms": latency_ms,
                    "tool_execution_ids": tool_execution_ids,
                    "tools_selected_count": selection.tools_selected_count,
                    "selected_tool_names": selection.selected_tool_names,
                    "provider_streaming": timing.get("provider_streaming"),
                    "time_to_first_token_ms": timing.get("model_time_to_first_token_ms"),
                    "total_generation_ms": timing.get("model_total_ms"),
                    "retrieval_ms": timing.get("retrieval_ms"),
                    "retrieved_chunk_count": timing.get("retrieved_chunk_count"),
                    "citation_count": timing.get("citation_count"),
                },
            )
            yield StreamEvent(
                event=StreamEventType.complete,
                data={"message": message_to_response(finalized).model_dump(mode="json")},
            )
            logger.info(
                "stream_completed user_id=%s conversation_id=%s message_id=%s "
                "retrieval_ms=%s model_ttft_ms=%s model_total_ms=%s "
                "total_request_ms=%s retrieved_chunk_count=%s citation_count=%s "
                "provider_streaming=%s request_id=%s",
                user.id,
                conversation.id,
                assistant.id,
                timing.get("retrieval_ms"),
                timing.get("model_time_to_first_token_ms"),
                timing.get("model_total_ms"),
                timing.get("total_request_ms"),
                timing.get("retrieved_chunk_count"),
                timing.get("citation_count"),
                timing.get("provider_streaming"),
                request_id,
            )
            try:
                for mem_event in await maybe_extract_after_turn(
                    session=session,
                    user=user,
                    conversation=conversation,
                    user_content=user_message.content,
                    assistant_content=finalized.content,
                    user_message_id=user_message.id,
                    memory_service=self.memory_service,
                    memory_extractor=self.memory_extractor,
                ):
                    yield mem_event
                await self._maybe_update_title(
                    session,
                    conversation,
                    user_message,
                    finalized,
                    prefer_fast=True,
                )
                await self._maybe_update_summary(session, conversation, user)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "stream_post_complete_failed conversation_id=%s message_id=%s " "request_id=%s",
                    conversation.id,
                    assistant.id,
                    request_id,
                )
            return

        accumulated = ""
        final_meta: dict[str, Any] = {}
        model_started = time.perf_counter()
        first_token_at = None
        try:
            async for event in self.llm_service.stream(generate_request):
                if event.event == StreamEventType.delta:
                    chunk = str(event.data.get("content") or "")
                    if chunk and first_token_at is None:
                        first_token_at = time.perf_counter()
                        timing["model_time_to_first_token_ms"] = round(
                            (first_token_at - model_started) * 1000, 2
                        )
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
            timing["model_total_ms"] = round((time.perf_counter() - model_started) * 1000, 2)
            timing["provider_streaming"] = True
        except asyncio.CancelledError:
            await self.message_service.cancel_assistant(
                session,
                assistant,
                partial_content=accumulated.strip(),
            )
            await session.commit()
            logger.info(
                "stream_cancelled conversation_id=%s message_id=%s "
                "partial_chars=%s request_id=%s",
                conversation.id,
                assistant.id,
                len(accumulated.strip()),
                request_id,
            )
            yield StreamEvent(
                event=StreamEventType.error,
                data={
                    "error": {
                        "code": "client_disconnected",
                        "message": "Generation cancelled",
                    }
                },
            )
            return
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

        if not general_mode and citations:
            accumulated = normalize_grounded_answer(accumulated)

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        timing["total_request_ms"] = latency_ms
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
                "provider_streaming": timing.get("provider_streaming"),
                "time_to_first_token_ms": timing.get("model_time_to_first_token_ms"),
                "total_generation_ms": timing.get("model_total_ms"),
                "retrieval_ms": timing.get("retrieval_ms"),
                "retrieved_chunk_count": timing.get("retrieved_chunk_count"),
                "citation_count": timing.get("citation_count"),
            },
        )
        yield StreamEvent(
            event=StreamEventType.complete,
            data={"message": message_to_response(finalized).model_dump(mode="json")},
        )
        logger.info(
            "stream_completed user_id=%s conversation_id=%s message_id=%s "
            "retrieval_ms=%s model_ttft_ms=%s model_total_ms=%s "
            "total_request_ms=%s retrieved_chunk_count=%s citation_count=%s "
            "provider_streaming=%s request_id=%s",
            user.id,
            conversation.id,
            assistant.id,
            timing.get("retrieval_ms"),
            timing.get("model_time_to_first_token_ms"),
            timing.get("model_total_ms"),
            timing.get("total_request_ms"),
            timing.get("retrieved_chunk_count"),
            timing.get("citation_count"),
            timing.get("provider_streaming"),
            request_id,
        )
        try:
            for mem_event in await maybe_extract_after_turn(
                session=session,
                user=user,
                conversation=conversation,
                user_content=user_message.content,
                assistant_content=finalized.content,
                user_message_id=user_message.id,
                memory_service=self.memory_service,
                memory_extractor=self.memory_extractor,
            ):
                yield mem_event
            await self._maybe_update_title(
                session,
                conversation,
                user_message,
                finalized,
                prefer_fast=True,
            )
            await self._maybe_update_summary(session, conversation, user)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "stream_post_complete_failed conversation_id=%s message_id=%s request_id=%s",
                conversation.id,
                assistant.id,
                request_id,
            )

    async def _maybe_update_title(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: Message,
        assistant: Message,
        *,
        prefer_fast: bool = False,
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
            if prefer_fast:
                # Avoid a blocking LLM call on the streaming critical path.
                title = user_message.content.strip()[:80] or DEFAULT_CONVERSATION_TITLE
            else:
                title = await self._generate_title(user_message.content, assistant.content)
            cleaned = self.conversation_service.sanitize_generated_title(title)
            conversation.title = cleaned
            conversation.title_is_auto = True
            conversation.updated_at = datetime.now(UTC)
            await session.flush()
            logger.info(
                "title_generation_success conversation_id=%s fast=%s request_id=%s",
                conversation.id,
                prefer_fast,
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
