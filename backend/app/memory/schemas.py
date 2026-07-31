"""Pydantic contracts for long-term memory APIs and internal pipelines."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MemoryCategory, MemoryConfidence, MemorySource, MemoryStatus


class MemoryIntentKind(StrEnum):
    none = "none"
    remember = "remember"
    forget = "forget"
    update = "update"
    list = "list"
    disable_for_conversation = "disable_for_conversation"


class MemoryCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10_000)
    category: MemoryCategory = MemoryCategory.other
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    expires_at: datetime | None = None
    confirmation_required: bool | None = None


class MemoryUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=10_000)
    category: MemoryCategory | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    expires_at: datetime | None = None


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: MemoryCategory
    status: MemoryStatus
    title: str
    content: str
    source: MemorySource
    confidence: MemoryConfidence | None = None
    importance: float
    confirmation_required: bool
    confirmed_at: datetime | None = None
    last_used_at: datetime | None = None
    use_count: int
    expires_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    version: int
    source_conversation_id: uuid.UUID | None = None


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    total: int
    limit: int
    offset: int


class MemorySettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_enabled: bool
    automatic_extraction_enabled: bool
    suggestions_enabled: bool
    require_confirmation: bool
    include_memories_in_chat: bool
    maximum_active_memories: int
    default_expiration_days: int | None = None
    created_at: datetime
    updated_at: datetime


class MemorySettingsUpdateRequest(BaseModel):
    memory_enabled: bool | None = None
    automatic_extraction_enabled: bool | None = None
    suggestions_enabled: bool | None = None
    require_confirmation: bool | None = None
    include_memories_in_chat: bool | None = None
    maximum_active_memories: int | None = Field(default=None, ge=1, le=500)
    default_expiration_days: int | None = Field(default=None, ge=1, le=3650)


class MemoryAuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    memory_id: uuid.UUID | None = None
    event_type: str
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    safe_metadata_json: dict[str, object] | None = None
    created_at: datetime
    correlation_id: str | None = None


class MemoryAuditListResponse(BaseModel):
    items: list[MemoryAuditEventResponse]
    total: int
    limit: int
    offset: int


class MemoryCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10_000)
    category: MemoryCategory = MemoryCategory.other
    confidence: MemoryConfidence = MemoryConfidence.medium
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)
    sensitive: bool = False
    duplicate_of: uuid.UUID | None = None
    recommended_expiration_days: int | None = Field(default=None, ge=1, le=3650)


class MemoryIntentResult(BaseModel):
    kind: MemoryIntentKind = MemoryIntentKind.none
    payload: str | None = None
    category: MemoryCategory | None = None
    confidence: float = 1.0


class RetrievedMemoryView(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    category: MemoryCategory
    relevance: float
    importance: float


class MemoryContextBlock(BaseModel):
    text: str
    memory_ids: list[uuid.UUID]
    count: int
    character_count: int


class MemoryReference(BaseModel):
    """Safe chat-facing memory reference (no IDs exposed to clients by default)."""

    title: str
    category: MemoryCategory


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
