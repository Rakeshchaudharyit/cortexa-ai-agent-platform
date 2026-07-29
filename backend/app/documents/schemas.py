"""Document and RAG Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import DocumentStatus


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
    processing_mode: Literal["synchronous"] = "synchronous"

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
