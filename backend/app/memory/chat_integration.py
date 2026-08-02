"""Chat ↔ long-term memory orchestration helpers."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.schemas import StreamEvent, StreamEventType
from app.memory.context import build_memory_context_block
from app.memory.exceptions import (
    MemoryAmbiguousForgetError,
    MemoryNotFoundError,
    MemorySensitiveContentError,
    MemoryValidationError,
)
from app.memory.extractor import MemoryExtractor
from app.memory.intent import detect_memory_intent
from app.memory.policies import may_extract_automatically, may_suggest
from app.memory.retrieval import MemoryRetriever
from app.memory.schemas import MemoryIntentKind, RetrievedMemoryView
from app.memory.service import MemoryService
from app.models.conversation import Conversation
from app.models.enums import MemorySource, MemoryStatus
from app.models.user import User

logger = logging.getLogger("cortexa.chat.memory")


@dataclass
class MemoryTurnResult:
    """Outcome of pre-generation memory handling for a chat turn."""

    memory_context: str = ""
    retrieved: list[RetrievedMemoryView] = field(default_factory=list)
    events: list[StreamEvent] = field(default_factory=list)
    short_circuit_reply: str | None = None
    memory_enabled: bool = True


async def prepare_memory_for_turn(
    *,
    session: AsyncSession,
    user: User,
    conversation: Conversation,
    user_content: str,
    user_message_id: uuid.UUID | None,
    memory_service: MemoryService | None,
    memory_retriever: MemoryRetriever | None,
    defer_persistent_writes: bool = False,
) -> MemoryTurnResult:
    result = MemoryTurnResult()
    if memory_service is None or not memory_service.settings.memory_enabled:
        result.memory_enabled = False
        return result

    try:
        settings = await memory_service.repository.get_or_create_settings(session, user)
    except Exception:
        logger.info("memory_settings_load_failed user_id=%s", user.id)
        result.memory_enabled = False
        return result

    active = memory_service.is_memory_active_for_conversation(
        settings,
        conversation_override=conversation.memory_enabled_override,
    )
    result.memory_enabled = active

    intent = detect_memory_intent(user_content)

    if intent.kind == MemoryIntentKind.disable_for_conversation:
        conversation.memory_enabled_override = False
        conversation.memory_disabled_reason = "user_request"
        result.events.append(
            StreamEvent(
                event=StreamEventType.memory_updated,
                data={"action": "disabled_for_conversation"},
            )
        )
        result.short_circuit_reply = (
            "Understood. I will not use long-term memory in this conversation. "
            "You can re-enable it anytime from the chat controls or /memories."
        )
        result.memory_enabled = False
        return result

    if not defer_persistent_writes and intent.kind == MemoryIntentKind.remember and intent.payload:
        try:
            memory = await memory_service.remember_explicit(
                session,
                user,
                intent.payload,
                category=intent.category,
                conversation_id=conversation.id,
                message_id=user_message_id,
            )
            event_type = (
                StreamEventType.memory_candidate_proposed
                if memory.status == MemoryStatus.proposed
                else StreamEventType.memory_saved
            )
            result.events.append(
                StreamEvent(
                    event=event_type,
                    data={
                        "title": memory.title,
                        "category": memory.category.value,
                        "status": memory.status.value,
                    },
                )
            )
            if memory.status == MemoryStatus.proposed:
                result.short_circuit_reply = (
                    f"I drafted a memory suggestion: “{memory.title}”. "
                    "Confirm it on the Memories page to start using it."
                )
            else:
                result.short_circuit_reply = f"Got it — I’ll remember: {memory.content}"
        except MemorySensitiveContentError as exc:
            result.events.append(
                StreamEvent(
                    event=StreamEventType.memory_action_failed,
                    data={"code": exc.code, "message": exc.message},
                )
            )
            result.short_circuit_reply = (
                "I can’t store that because it looks like sensitive information "
                "(for example a password, API key, or token)."
            )
        except MemoryValidationError as exc:
            result.events.append(
                StreamEvent(
                    event=StreamEventType.memory_action_failed,
                    data={"code": exc.code, "message": exc.message},
                )
            )
            result.short_circuit_reply = exc.message
        except Exception:
            logger.info("memory_remember_failed user_id=%s", user.id)
            result.events.append(
                StreamEvent(
                    event=StreamEventType.memory_action_failed,
                    data={"code": "memory_action_failed", "message": "Could not save memory"},
                )
            )
            result.short_circuit_reply = "I couldn’t save that memory right now."
        return result

    if not defer_persistent_writes and intent.kind == MemoryIntentKind.forget and intent.payload:
        try:
            forgotten = await memory_service.forget_matching(
                session,
                user,
                intent.payload,
                conversation_id=conversation.id,
            )
            titles = ", ".join(m.title for m in forgotten)
            result.events.append(
                StreamEvent(
                    event=StreamEventType.memory_archived,
                    data={"count": len(forgotten), "titles": [m.title for m in forgotten]},
                )
            )
            result.short_circuit_reply = f"Removed from active memory: {titles}."
        except MemoryAmbiguousForgetError as exc:
            result.events.append(
                StreamEvent(
                    event=StreamEventType.memory_action_failed,
                    data={"code": exc.code, "message": exc.message},
                )
            )
            result.short_circuit_reply = exc.message
        except MemoryNotFoundError:
            result.short_circuit_reply = "I couldn’t find a matching memory to forget."
        except Exception:
            logger.info("memory_forget_failed user_id=%s", user.id)
            result.short_circuit_reply = "I couldn’t forget that memory right now."
        return result

    if not defer_persistent_writes and intent.kind == MemoryIntentKind.update and intent.payload:
        try:
            memory = await memory_service.remember_explicit(
                session,
                user,
                intent.payload,
                category=intent.category,
                conversation_id=conversation.id,
                message_id=user_message_id,
            )
            result.events.append(
                StreamEvent(
                    event=StreamEventType.memory_updated,
                    data={
                        "title": memory.title,
                        "category": memory.category.value,
                        "status": memory.status.value,
                    },
                )
            )
            result.short_circuit_reply = f"Updated preference: {memory.content}"
        except Exception as exc:
            message = getattr(exc, "message", "Could not update memory")
            result.short_circuit_reply = str(message)
        return result

    if intent.kind == MemoryIntentKind.list:
        try:
            items = await memory_service.list_for_prompt(
                session, user, query=intent.payload, limit=10
            )
            if not items:
                result.short_circuit_reply = "I don’t have any active memories stored yet."
            else:
                lines = [f"- [{m.category.value}] {m.content}" for m in items[:10]]
                result.short_circuit_reply = "Here’s what I remember:\n" + "\n".join(lines)
        except Exception:
            result.short_circuit_reply = "I couldn’t list memories right now."
        return result

    if not active or memory_retriever is None:
        return result

    result.events.append(StreamEvent(event=StreamEventType.memory_retrieval_started, data={}))
    try:
        retrieved = await memory_retriever.retrieve(
            session,
            user,
            query=user_content,
        )
        block = build_memory_context_block(
            retrieved,
            max_characters=memory_service.settings.memory_context_max_characters,
        )
        result.retrieved = retrieved
        result.memory_context = block.text
        if block.memory_ids:
            await memory_service.repository.mark_used(session, block.memory_ids, user.id)
            await memory_service.repository.add_audit(
                session,
                user_id=user.id,
                event_type=__import__(
                    "app.models.enums", fromlist=["MemoryAuditEventType"]
                ).MemoryAuditEventType.retrieved,
                conversation_id=conversation.id,
                message_id=user_message_id,
                safe_metadata={"count": block.count},
            )
            conversation.memory_context_used = (
                int(conversation.memory_context_used or 0) + block.count
            )
        result.events.append(
            StreamEvent(
                event=StreamEventType.memory_retrieval_completed,
                data={
                    "count": block.count,
                    "references": [
                        {"title": m.title, "category": m.category.value}
                        for m in retrieved[: block.count]
                    ],
                },
            )
        )
    except Exception:
        logger.info("memory_retrieval_degraded user_id=%s", user.id)
        result.events.append(
            StreamEvent(
                event=StreamEventType.memory_retrieval_completed,
                data={"count": 0},
            )
        )
    return result


async def maybe_extract_after_turn(
    *,
    session: AsyncSession,
    user: User,
    conversation: Conversation,
    user_content: str,
    assistant_content: str,
    user_message_id: uuid.UUID | None,
    memory_service: MemoryService | None,
    memory_extractor: MemoryExtractor | None,
) -> list[StreamEvent]:
    events: list[StreamEvent] = []
    if memory_service is None or memory_extractor is None:
        return events
    if not memory_service.settings.memory_enabled:
        return events
    try:
        settings = await memory_service.repository.get_or_create_settings(session, user)
        if conversation.memory_enabled_override is False:
            return events
        suggest = may_suggest(
            memory_enabled=settings.memory_enabled,
            suggestions_enabled=settings.suggestions_enabled,
        )
        auto = may_extract_automatically(
            memory_enabled=settings.memory_enabled,
            automatic_extraction_enabled=settings.automatic_extraction_enabled,
        )
        if not suggest and not auto:
            return events
        candidates = await memory_extractor.extract_from_turn(
            user_content=user_content,
            assistant_content=assistant_content,
        )
        for candidate in candidates[:3]:
            source = (
                MemorySource.automatic_extraction if auto else MemorySource.assistant_suggestion
            )
            memory = await memory_service.propose_candidate(
                session,
                user,
                title=candidate.title,
                content=candidate.content,
                category=candidate.category,
                confidence=candidate.confidence,
                importance=candidate.importance,
                source=source,
                source_conversation_id=conversation.id,
                source_message_id=user_message_id,
            )
            if memory is None:
                continue
            # Auto-confirm only when extraction is on AND confirmation is not required.
            if (
                auto
                and not settings.require_confirmation
                and memory.status == MemoryStatus.proposed
            ):
                try:
                    await memory_service.confirm(session, user, memory.id)
                    events.append(
                        StreamEvent(
                            event=StreamEventType.memory_saved,
                            data={
                                "title": memory.title,
                                "category": memory.category.value,
                                "status": "active",
                            },
                        )
                    )
                    continue
                except Exception:
                    pass
            events.append(
                StreamEvent(
                    event=StreamEventType.memory_candidate_proposed,
                    data={
                        "title": memory.title,
                        "category": memory.category.value,
                        "reason": candidate.reason,
                        "status": memory.status.value,
                    },
                )
            )
    except Exception:
        logger.info("memory_extraction_after_turn_failed user_id=%s", user.id)
    return events
