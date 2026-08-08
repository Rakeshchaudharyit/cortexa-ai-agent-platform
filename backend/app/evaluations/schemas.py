"""Pydantic contracts for admin RAG evaluations."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCaseCreate(BaseModel):
    owner_user_id: uuid.UUID
    name: str = Field(min_length=2, max_length=160)
    question: str = Field(min_length=3, max_length=4000)
    expected_answer: str | None = Field(default=None, max_length=8000)
    expected_keywords: list[str] = Field(default_factory=list, max_length=30)
    expected_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    should_answer: bool = True
    enabled: bool = True


class EvaluationCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    question: str | None = Field(default=None, min_length=3, max_length=4000)
    expected_answer: str | None = Field(default=None, max_length=8000)
    expected_keywords: list[str] | None = Field(default=None, max_length=30)
    expected_document_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    should_answer: bool | None = None
    enabled: bool | None = None


class EvaluationCaseView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    question: str
    expected_answer: str | None
    expected_keywords: list[str]
    expected_document_ids: list[uuid.UUID]
    should_answer: bool
    enabled: bool
    created_at: datetime
    updated_at: datetime


class EvaluationCaseList(BaseModel):
    items: list[EvaluationCaseView]
    total: int


class EvaluationResultView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    case_id: uuid.UUID | None
    case_name: str
    status: str
    score: float
    passed: bool
    groundedness_score: float
    keyword_recall_score: float
    citation_match_score: float
    answerability_score: float
    retrieval_count: int
    citation_count: int
    latency_ms: float | None
    provider: str | None
    model: str | None
    answer_excerpt: str | None
    error_code: str | None
    created_at: datetime


class EvaluationRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_score: float
    provider: str | None
    model: str | None
    duration_ms: float | None
    error_summary: str | None
    created_at: datetime
    completed_at: datetime | None
    background_job_id: uuid.UUID | None = None


class EvaluationRunDetail(EvaluationRunView):
    results: list[EvaluationResultView]


class EvaluationRunList(BaseModel):
    items: list[EvaluationRunView]
    total: int
