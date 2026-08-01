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
