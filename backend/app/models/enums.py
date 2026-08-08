"""Shared database enums for authentication, users, and documents."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Application roles — admin unlocks the enterprise administration portal."""

    user = "user"
    admin = "admin"


class UserStatus(StrEnum):
    """Account status controls enforced server-side."""

    active = "active"
    disabled = "disabled"


class DocumentStatus(StrEnum):
    """Document ingestion lifecycle."""

    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ConversationStatus(StrEnum):
    """Conversation lifecycle — archived conversations reject new messages."""

    active = "active"
    archived = "archived"


class MessageRole(StrEnum):
    """Persisted chat message roles. System messages are internal-only."""

    user = "user"
    assistant = "assistant"
    system = "system"


class MessageStatus(StrEnum):
    """Message lifecycle for streaming and failed generations."""

    pending = "pending"
    complete = "complete"
    failed = "failed"
    dead_lettered = "dead_lettered"
    cancelled = "cancelled"


class ToolExecutionStatus(StrEnum):
    """Lifecycle for audited agent tool executions."""

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    denied = "denied"
    timed_out = "timed_out"
    cancelled = "cancelled"


class MemoryCategory(StrEnum):
    """Durable long-term memory categories (non-sensitive identity)."""

    preference = "preference"
    personal_context = "personal_context"
    project = "project"
    instruction = "instruction"
    workflow = "workflow"
    technical_context = "technical_context"
    decision = "decision"
    goal = "goal"
    relationship_context = "relationship_context"
    other = "other"


class MemorySource(StrEnum):
    """How a memory entered the system."""

    explicit_user_request = "explicit_user_request"
    assistant_suggestion = "assistant_suggestion"
    automatic_extraction = "automatic_extraction"
    imported = "imported"
    system_generated = "system_generated"


class MemoryStatus(StrEnum):
    """Long-term memory lifecycle."""

    proposed = "proposed"
    active = "active"
    archived = "archived"
    rejected = "rejected"
    deleted = "deleted"


class MemoryConfidence(StrEnum):
    """Coarse confidence for extracted or proposed memories."""

    high = "high"
    medium = "medium"
    low = "low"


class MemoryAuditEventType(StrEnum):
    """Audited memory lifecycle events."""

    proposed = "proposed"
    created = "created"
    confirmed = "confirmed"
    updated = "updated"
    retrieved = "retrieved"
    injected = "injected"
    archived = "archived"
    restored = "restored"
    rejected = "rejected"
    deleted = "deleted"
    expired = "expired"
    conflict_superseded = "conflict_superseded"


class AgentExecutionMode(StrEnum):
    """Whether a run uses the single-agent chat path or multi-agent coordination."""

    single_agent = "single_agent"
    multi_agent = "multi_agent"


class AgentRunStatus(StrEnum):
    """Lifecycle for a bounded multi-agent run."""

    pending = "pending"
    planning = "planning"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"
    dead_lettered = "dead_lettered"
    cancelled = "cancelled"
    timed_out = "timed_out"


class AgentTaskStatus(StrEnum):
    """Lifecycle for an individual agent task within a run."""

    pending = "pending"
    ready = "ready"
    running = "running"
    awaiting_approval = "awaiting_approval"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"
    cancelled = "cancelled"
    timed_out = "timed_out"


class AgentApprovalStatus(StrEnum):
    """User approval resolution for sensitive write actions."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    cancelled = "cancelled"


class JobStatus(StrEnum):
    """Durable background job lifecycle."""

    queued = "queued"
    running = "running"
    retrying = "retrying"
    succeeded = "succeeded"
    failed = "failed"
    dead_lettered = "dead_lettered"
    cancelled = "cancelled"
