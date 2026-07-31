"""Conversation summary tool — owner-scoped, non-recursive, LLM-backed."""

from __future__ import annotations

import uuid
from typing import ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.llm.schemas import ChatMessage, GenerateRequest
from app.llm.schemas import MessageRole as LLMRole
from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole
from app.tools.base import BaseTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import (
    ToolExecutionFailedError,
    ToolInvalidArgumentsError,
    ToolPermissionDeniedError,
)
from app.tools.schemas import ToolResultPayload

_DEFAULT_MAX_MESSAGES = 50
_HARD_MAX_MESSAGES = 50
_MAX_SUMMARY_CHARS = 2000
_MAX_INPUT_CHARS = 24_000


class ConversationSummaryInput(BaseModel):
    conversation_id: uuid.UUID
    max_messages: int = Field(default=_DEFAULT_MAX_MESSAGES, ge=1, le=_HARD_MAX_MESSAGES)


class ConversationSummaryOutput(BaseModel):
    conversation_id: uuid.UUID
    message_count: int
    summary: str
    empty: bool = False


class ConversationSummaryTool(BaseTool):
    name: ClassVar[str] = "conversation_summary"
    description: ClassVar[str] = (
        "Summarize a conversation owned by the current user. "
        "Provide conversation_id and optional max_messages (1-50). "
        "Do not call this tool recursively."
    )
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "conversation"
    input_model: ClassVar[type[BaseModel]] = ConversationSummaryInput
    output_model: ClassVar[type[BaseModel] | None] = ConversationSummaryOutput
    timeout_seconds: ClassVar[int] = 90

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, ConversationSummaryInput)

        # Prevent recursive self-invocation within the same agent turn.
        if self.name in context.active_tool_stack[:-1]:
            raise ToolExecutionFailedError("conversation_summary cannot be invoked recursively")

        conversation = await context.session.scalar(
            select(Conversation).where(Conversation.id == arguments.conversation_id)
        )
        if conversation is None:
            raise ToolInvalidArgumentsError("Conversation not found")
        if conversation.user_id != context.user_id:
            raise ToolPermissionDeniedError(self.name)

        limit = min(arguments.max_messages, _HARD_MAX_MESSAGES)
        result = await context.session.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.user_id == context.user_id,
                Message.is_active.is_(True),
                Message.role.in_([MessageRole.user, MessageRole.assistant]),
            )
            .order_by(Message.sequence_number.asc())
            .limit(limit)
            .options(selectinload(Message.citations))
        )
        messages = list(result.all())
        if not messages:
            payload = ConversationSummaryOutput(
                conversation_id=conversation.id,
                message_count=0,
                summary="This conversation has no messages yet.",
                empty=True,
            )
            return ToolResultPayload(success=True, data=payload.model_dump(mode="json"))

        llm = context.llm_service
        if llm is None:
            raise ToolExecutionFailedError("Conversation summary is not configured")

        transcript_parts: list[str] = []
        total_chars = 0
        for message in messages:
            # Exclude sensitive internal fields — content + role only.
            line = f"{message.role.value}: {message.content.strip()}"
            if total_chars + len(line) > _MAX_INPUT_CHARS:
                break
            transcript_parts.append(line)
            total_chars += len(line) + 1
        transcript = "\n".join(transcript_parts)

        try:
            generation = await llm.generate(
                GenerateRequest(
                    messages=[
                        ChatMessage(
                            role=LLMRole.user,
                            content=(
                                "Summarize the following conversation briefly. "
                                "Focus on user goals, key facts, and outcomes. "
                                "Do not invent details.\n\n"
                                f"{transcript}"
                            ),
                        )
                    ],
                    system=(
                        "You summarize conversations. Return a concise plain-text "
                        "summary only. Never call tools."
                    ),
                    temperature=0.2,
                    max_tokens=256,
                )
            )
        except Exception as exc:
            from app.core.exceptions import AppError

            if isinstance(exc, AppError):
                raise ToolExecutionFailedError(exc.message) from exc
            raise ToolExecutionFailedError("Failed to generate conversation summary") from exc

        summary = (generation.content or "").strip()
        if len(summary) > _MAX_SUMMARY_CHARS:
            summary = summary[:_MAX_SUMMARY_CHARS].rstrip() + "…"
        if not summary:
            summary = "Unable to produce a summary for this conversation."

        payload = ConversationSummaryOutput(
            conversation_id=conversation.id,
            message_count=len(messages),
            summary=summary,
            empty=False,
        )
        return ToolResultPayload(success=True, data=payload.model_dump(mode="json"))
