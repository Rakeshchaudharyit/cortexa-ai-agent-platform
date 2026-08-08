"""Pydantic contracts for background jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    job_type: str = Field(default="demo.validation", min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    max_attempts: int = Field(default=3, ge=1, le=10)


class JobResponse(BaseModel):
    id: UUID
    owner_user_id: UUID | None
    job_type: str
    status: str
    progress_percent: int
    status_message: str | None
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    attempt_count: int
    max_attempts: int
    cancellation_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime
    resource_type: str | None = None
    resource_id: str | None = None


class JobQueueMetrics(BaseModel):
    ready_depth: int = 0
    delayed_depth: int = 0
    dead_letter_count: int = 0
    stale_running_count: int = 0
    oldest_queued_age_seconds: int | None = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    worker_healthy: bool
    worker_last_seen_at: datetime | None = None
    queue_metrics: JobQueueMetrics = Field(default_factory=JobQueueMetrics)


class JobBulkActionRequest(BaseModel):
    job_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: str = Field(pattern="^(cancel|requeue)$")


class JobBulkActionResponse(BaseModel):
    action: str
    requested: int
    changed: int
    skipped: int
