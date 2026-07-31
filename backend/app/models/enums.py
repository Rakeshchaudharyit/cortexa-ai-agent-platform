"""Shared database enums for authentication, users, and documents."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Role foundation — admin capabilities arrive in a later phase."""

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
