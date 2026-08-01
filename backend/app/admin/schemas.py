"""Pydantic schemas for enterprise administration APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    ConversationStatus,
    DocumentStatus,
    MemoryCategory,
    MemorySource,
    MemoryStatus,
    ToolExecutionStatus,
    UserRole,
    UserStatus,
)


class AdminPaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


# ── Dashboard ──────────────────────────────────────────────────────────────


class AdminMetricCard(BaseModel):
    key: str
    label: str
    value: int | float | None
    unit: str | None = None
    unavailable: bool = False
    hint: str | None = None


class AdminTrendPoint(BaseModel):
    date: str
    conversations: int = 0
    messages: int = 0
    tool_executions: int = 0


class AdminStatusCount(BaseModel):
    status: str
    count: int


class AdminToolUsageStat(BaseModel):
    tool_name: str
    executions: int
    succeeded: int
    failed: int
    success_rate: float | None = None


class AdminRecentActivityItem(BaseModel):
    kind: str
    summary: str
    created_at: datetime
    actor_email: str | None = None
    target_type: str | None = None


class AdminSystemStatusSummary(BaseModel):
    backend: str
    postgres: str
    redis: str
    ollama: str
    embedding_model: str
    migrations: str
    storage: str
    database_identity: str | None = None
    app_version: str | None = None
    environment: str | None = None


class AdminAiActivitySummary(BaseModel):
    provider: str
    model: str
    average_latency_ms: float | None = None
    successful_requests: int | None = None
    failed_requests: int | None = None
    available: bool | None = None
    note: str | None = None


class AdminDashboardResponse(BaseModel):
    metrics: list[AdminMetricCard]
    usage_trend: list[AdminTrendPoint]
    ai_activity: AdminAiActivitySummary
    document_pipeline: list[AdminStatusCount]
    tool_usage: list[AdminToolUsageStat]
    recent_activity: list[AdminRecentActivityItem]
    system_status: AdminSystemStatusSummary
    generated_at: datetime


# ── Users ──────────────────────────────────────────────────────────────────


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    status: UserStatus
    is_email_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None
    conversations_count: int = 0
    documents_count: int = 0
    memories_count: int = 0


class AdminUserDetail(AdminUserSummary):
    active_sessions_count: int = 0
    tool_executions_count: int = 0
    tool_success_count: int = 0
    tool_failure_count: int = 0
    recent_activity: list[AdminRecentActivityItem] = Field(default_factory=list)


class AdminUserListResponse(AdminPaginationMeta):
    items: list[AdminUserSummary]


class AdminUserUpdateRequest(BaseModel):
    role: UserRole | None = None
    status: UserStatus | None = None

    @field_validator("role", "status")
    @classmethod
    def at_least_one(cls, value: Any) -> Any:
        return value


class AdminUserUpdateResponse(BaseModel):
    user: AdminUserDetail
    sessions_revoked: int = 0


class AdminRevokeSessionsResponse(BaseModel):
    user_id: uuid.UUID
    sessions_revoked: int


# ── Documents ──────────────────────────────────────────────────────────────


class AdminDocumentSummary(BaseModel):
    id: uuid.UUID
    filename: str
    owner_id: uuid.UUID
    owner_email: str | None = None
    owner_name: str | None = None
    media_type: str | None = None
    status: DocumentStatus
    size_bytes: int | None = None
    chunk_count: int = 0
    created_at: datetime
    processed_at: datetime | None = None
    processing_duration_ms: float | None = None
    error_code: str | None = None


class AdminDocumentDetail(AdminDocumentSummary):
    checksum: str | None = None
    storage_key: str | None = None
    character_count: int | None = None
    embedding_dimension: int | None = None
    error_message: str | None = None
    excerpt_samples: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class AdminDocumentListResponse(AdminPaginationMeta):
    items: list[AdminDocumentSummary]


# ── Conversations ──────────────────────────────────────────────────────────


class AdminConversationSummary(BaseModel):
    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    owner_email: str | None = None
    owner_name: str | None = None
    status: ConversationStatus
    message_count: int = 0
    last_activity_at: datetime | None = None
    grounded_mode: bool | None = None
    memory_enabled: bool | None = None
    tool_execution_count: int = 0
    created_at: datetime


class AdminConversationDetail(AdminConversationSummary):
    citations_count: int = 0
    memory_use_count: int = 0
    average_latency_ms: float | None = None
    failed_message_count: int = 0
    tool_timeline: list[dict[str, Any]] = Field(default_factory=list)


class AdminConversationListResponse(AdminPaginationMeta):
    items: list[AdminConversationSummary]


# ── Memories ───────────────────────────────────────────────────────────────


class AdminMemorySummary(BaseModel):
    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    owner_email: str | None = None
    owner_name: str | None = None
    category: MemoryCategory
    status: MemoryStatus
    source: MemorySource
    created_at: datetime
    last_used_at: datetime | None = None
    use_count: int = 0


class AdminMemoryDetail(AdminMemorySummary):
    confidence: str | None = None
    importance: int | None = None
    content_preview: str | None = None
    content_redacted: bool = False
    audit_events: list[dict[str, Any]] = Field(default_factory=list)
    warning: str | None = (
        "Memory content is private user data. Access is audited. " "Do not edit silently."
    )


class AdminMemoryListResponse(AdminPaginationMeta):
    items: list[AdminMemorySummary]


# ── Tools ──────────────────────────────────────────────────────────────────


class AdminToolSummary(BaseModel):
    name: str
    category: str
    version: str
    description: str
    enabled: bool
    registry_enabled: bool
    required_roles: list[str]
    timeout_seconds: int
    confirmation_required: bool
    execution_count: int = 0
    success_rate: float | None = None
    average_duration_ms: float | None = None
    has_configuration: bool = False


class AdminToolListResponse(BaseModel):
    tools: list[AdminToolSummary]
    total: int


class AdminToolUpdateRequest(BaseModel):
    enabled: bool | None = None
    timeout_override: int | None = Field(default=None, ge=1, le=300)
    confirmation_required_override: bool | None = None


class AdminToolUpdateResponse(BaseModel):
    tool: AdminToolSummary


# ── Tool executions ────────────────────────────────────────────────────────


class AdminToolExecutionSummary(BaseModel):
    id: uuid.UUID
    tool_name: str
    user_id: uuid.UUID
    user_email: str | None = None
    conversation_id: uuid.UUID | None = None
    status: ToolExecutionStatus
    started_at: datetime
    duration_ms: float | None = None
    error_code: str | None = None
    created_at: datetime


class AdminToolExecutionDetail(AdminToolExecutionSummary):
    arguments_summary: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    error_message: str | None = None
    correlation_id: str | None = None
    completed_at: datetime | None = None


class AdminToolExecutionListResponse(AdminPaginationMeta):
    items: list[AdminToolExecutionSummary]


# ── Analytics ──────────────────────────────────────────────────────────────


class AdminAnalyticsPoint(BaseModel):
    date: str
    daily_active_users: int = 0
    new_users: int = 0
    conversations: int = 0
    messages: int = 0
    document_uploads: int = 0
    rag_queries: int = 0
    memory_actions: int = 0
    tool_executions: int = 0
    tool_succeeded: int = 0
    tool_failed: int = 0
    ai_latency_ms: float | None = None
    retrieval_latency_ms: float | None = None
    first_token_latency_ms: float | None = None


class AdminAnalyticsResponse(BaseModel):
    range_days: Literal[7, 30, 90]
    points: list[AdminAnalyticsPoint]
    totals: dict[str, int | float | None]
    unavailable: list[str] = Field(default_factory=list)
    generated_at: datetime


# ── Audit ──────────────────────────────────────────────────────────────────


class AdminAuditEventSummary(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    actor_email: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    target_user_id: uuid.UUID | None = None
    safe_summary: str
    metadata_json: dict[str, Any] | None = None
    request_id: str | None = None
    created_at: datetime


class AdminAuditListResponse(AdminPaginationMeta):
    items: list[AdminAuditEventSummary]


# ── System ─────────────────────────────────────────────────────────────────


class AdminSystemComponentStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "unavailable", "unknown"]
    message: str | None = None
    detail: str | None = None


class AdminSystemHealthResponse(BaseModel):
    overall: Literal["ok", "degraded", "unavailable"]
    components: list[AdminSystemComponentStatus]
    ai_configuration: dict[str, Any]
    application: dict[str, Any]
    refreshed_at: datetime
    guidance: list[str] = Field(default_factory=list)


# ── Settings ───────────────────────────────────────────────────────────────


class AdminSettingItem(BaseModel):
    key: str
    value: Any
    source: Literal["default", "override", "runtime"]
    editable: bool
    description: str | None = None


class AdminSettingsResponse(BaseModel):
    settings: list[AdminSettingItem]
    runtime: dict[str, Any]
    unsafe_keys_blocked: list[str]


class AdminSettingsUpdateRequest(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)

    @field_validator("updates")
    @classmethod
    def non_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("At least one setting update is required")
        if len(value) > 40:
            raise ValueError("Too many settings in a single update")
        return value


class AdminSettingsUpdateResponse(BaseModel):
    settings: list[AdminSettingItem]
    updated_keys: list[str]
