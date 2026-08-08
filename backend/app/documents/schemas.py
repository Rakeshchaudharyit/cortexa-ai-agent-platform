"""Document and RAG Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DocumentStatus


class DocumentFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Folder name cannot be blank")
        return cleaned


class DocumentFolderResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentFolderListResponse(BaseModel):
    items: list[DocumentFolderResponse]
    total: int


class DocumentMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    folder_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            tag = " ".join(value.split()).lower()[:50]
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned


class KnowledgeDocumentEventResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID | None = None
    event_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DocumentVersionSummary(BaseModel):
    id: uuid.UUID
    version_number: int
    title: str | None = None
    original_filename: str
    lifecycle_state: str
    is_active_version: bool
    status: DocumentStatus
    chunk_count: int
    character_count: int
    created_at: datetime
    processed_at: datetime | None = None
    archived_at: datetime | None = None


class DocumentVersionHistoryResponse(BaseModel):
    knowledge_document_id: uuid.UUID
    title: str
    active_version_id: uuid.UUID | None = None
    versions: list[DocumentVersionSummary]


class DocumentTimelineResponse(BaseModel):
    knowledge_document_id: uuid.UUID
    items: list[KnowledgeDocumentEventResponse]


class DocumentVersionCompareResponse(BaseModel):
    left: DocumentVersionSummary
    right: DocumentVersionSummary
    changed_fields: list[str]
    chunk_count_delta: int
    character_count_delta: int


class DocumentResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    media_type: str
    file_size_bytes: int
    status: DocumentStatus
    chunk_count: int
    character_count: int
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    title: str | None = None
    folder_id: uuid.UUID | None = None
    folder_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    version_number: int = 1
    knowledge_document_id: uuid.UUID | None = None
    lifecycle_state: str = "active"
    is_active_version: bool = True
    supersedes_document_id: uuid.UUID | None = None
    archived_at: datetime | None = None
    is_archived: bool = False
    processing_mode: Literal["synchronous", "background"] = "background"
    background_job_id: uuid.UUID | None = None
    job_status: str | None = None
    job_progress_percent: int | None = None
    job_status_message: str | None = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class ExtractedSegment(BaseModel):
    text: str
    page_number: int | None = None
    section: str | None = None
    paragraph_index: int | None = None


class ExtractionResult(BaseModel):
    text: str
    character_count: int
    media_type: str
    segments: list[ExtractedSegment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextChunk(BaseModel):
    index: int
    content: str
    character_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    top_k: int | None = Field(default=None, ge=1, le=100)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question cannot be blank")
        return cleaned


class RagCitation(BaseModel):
    citation_id: str
    document_id: uuid.UUID
    filename: str
    chunk_id: uuid.UUID
    chunk_index: int
    page_number: int | None = None
    excerpt: str
    similarity: float


class RagQueryResponse(BaseModel):
    answer: str
    citations: list[RagCitation]
    retrieval_count: int
    model: str
    provider: str
    grounded: bool
    latency_ms: float | None = None


class EmbeddingStatusResponse(BaseModel):
    provider: str
    model: str
    provider_reachable: bool
    model_available: bool
    configured_dimension: int
    status: str
    message: str
