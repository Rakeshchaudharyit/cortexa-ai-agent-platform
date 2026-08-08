"""Safe request/response schemas for Phase 5 conversations."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.feedback_schemas import MessageFeedbackView
from app.tools.schemas import ToolExecutionSummary

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_title(value: str, *, max_length: int = 200) -> str:
    cleaned = _CONTROL_CHARS.sub("", value).strip()
    if not cleaned:
        raise ValueError("Title cannot be blank")
    if len(cleaned) > max_length:
        raise ValueError(f"Title exceeds {max_length} characters")
    return cleaned


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    initial_message: str | None = Field(default=None, max_length=100_000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return sanitize_title(value)

    @field_validator("initial_message")
    @classmethod
    def validate_initial_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Initial message cannot be blank")
        return cleaned


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return sanitize_title(value)


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    archived_at: datetime | None = None
    title_is_auto: bool
    summary_preview: str | None = None
    memory_enabled: bool | None = None


class ConversationMemoryUpdateRequest(BaseModel):
    memory_enabled: bool
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class MessageCitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    citation_index: int
    citation_id: str
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
    filename: str
    page_number: int | None = None
    chunk_index: int
    excerpt: str
    similarity_score: float | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    status: str
    sequence_number: int
    is_active: bool
    grounded: bool | None = None
    model: str | None = None
    provider: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    finish_reason: str | None = None
    error_code: str | None = None
    regenerated_from_message_id: uuid.UUID | None = None
    edited_from_message_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    citations: list[MessageCitationResponse] = Field(default_factory=list)
    tool_execution_ids: list[str] = Field(default_factory=list)
    tool_executions: list[ToolExecutionSummary] = Field(default_factory=list)
    agent_run_id: str | None = None
    feedback: MessageFeedbackView | None = None


class ConversationDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    archived_at: datetime | None = None
    title_is_auto: bool
    summary: str | None = None
    default_document_scope: list[uuid.UUID] | None = None
    messages: list[MessageResponse]
    has_more_messages: bool = False
    memory_enabled: bool | None = None
    memory_context_used: int = 0
    active_agent_run_id: uuid.UUID | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationSummaryResponse]
    total: int
    limit: int
    offset: int


class CreateMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    top_k: int | None = Field(default=None, ge=1, le=100)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    client_request_id: uuid.UUID | None = None
    force_multi_agent: bool = False
    execution_profile: Literal["fast", "balanced", "deep"] = "fast"

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message content cannot be blank")
        return cleaned


class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message content cannot be blank")
        return cleaned


class RegenerateRequest(BaseModel):
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    top_k: int | None = Field(default=None, ge=1, le=100)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    client_request_id: uuid.UUID | None = None


class CreateMessageResponse(BaseModel):
    conversation: ConversationSummaryResponse
    user_message: MessageResponse
    assistant_message: MessageResponse


class UsageSummaryResponse(BaseModel):
    conversations: int
    active_conversations: int
    messages: int
    user_messages: int
    assistant_messages: int
    documents: int
    known_prompt_tokens: int
    known_completion_tokens: int
    known_total_tokens: int
    average_latency_ms: float | None = None
