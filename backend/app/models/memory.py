"""Long-term user memory models for Phase 7 personalization."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.document import EMBEDDING_DIMENSION
from app.models.enums import (
    MemoryAuditEventType,
    MemoryCategory,
    MemoryConfidence,
    MemorySource,
    MemoryStatus,
)

if TYPE_CHECKING:
    from app.models.conversation import Conversation, Message
    from app.models.user import User


class UserMemory(Base):
    """User-owned durable memory distinct from conversation history and RAG."""

    __tablename__ = "user_memories"
    __table_args__ = (
        Index("ix_user_memories_user_id_status", "user_id", "status"),
        Index("ix_user_memories_user_id_category", "user_id", "category"),
        Index("ix_user_memories_user_id_updated_at", "user_id", "updated_at"),
        Index("ix_user_memories_user_id_last_used_at", "user_id", "last_used_at"),
        Index("ix_user_memories_normalized_content", "user_id", "normalized_content"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[MemoryCategory] = mapped_column(
        Enum(
            MemoryCategory,
            name="memory_category",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=MemoryCategory.other,
        server_default=MemoryCategory.other.value,
    )
    status: Mapped[MemoryStatus] = mapped_column(
        Enum(
            MemoryStatus,
            name="memory_status",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=MemoryStatus.proposed,
        server_default=MemoryStatus.proposed.value,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(String(2000), nullable=False)
    source: Mapped[MemorySource] = mapped_column(
        Enum(
            MemorySource,
            name="memory_source",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
        default=MemorySource.explicit_user_request,
        server_default=MemorySource.explicit_user_request.value,
    )
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    confidence: Mapped[MemoryConfidence | None] = mapped_column(
        Enum(
            MemoryConfidence,
            name="memory_confidence",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    importance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        server_default="0.5",
    )
    confirmation_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    use_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    memory_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata_json",
        JSONB,
        nullable=True,
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=True,
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_memories.id", ondelete="SET NULL"),
        nullable=True,
    )

    user: Mapped[User] = relationship("User", back_populates="memories")
    source_conversation: Mapped[Conversation | None] = relationship(
        "Conversation",
        foreign_keys=[source_conversation_id],
    )
    source_message: Mapped[Message | None] = relationship(
        "Message",
        foreign_keys=[source_message_id],
    )

    def __repr__(self) -> str:
        return f"<UserMemory id={self.id} status={self.status} category={self.category}>"


class UserMemorySettings(Base):
    """Per-user long-term memory preferences with safe defaults."""

    __tablename__ = "user_memory_settings"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_memory_settings_user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    automatic_extraction_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    suggestions_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    require_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    include_memories_in_chat: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    maximum_active_memories: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
    )
    default_expiration_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship("User", back_populates="memory_settings")

    def __repr__(self) -> str:
        return f"<UserMemorySettings user_id={self.user_id} enabled={self.memory_enabled}>"


class MemoryAuditEvent(Base):
    """Append-only audit trail for memory lifecycle actions."""

    __tablename__ = "memory_audit_events"
    __table_args__ = (
        Index("ix_memory_audit_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_memory_audit_events_memory_id", "memory_id"),
        Index("ix_memory_audit_events_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_memories.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[MemoryAuditEventType] = mapped_column(
        Enum(
            MemoryAuditEventType,
            name="memory_audit_event_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    safe_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<MemoryAuditEvent id={self.id} type={self.event_type}>"
