"""Enterprise administration models — settings, tool config, and audit events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PlatformSetting(Base):
    """Database-backed safe platform setting overrides.

    Only keys allowlisted by the admin settings policy may be stored.
    Secrets, connection strings, and production security flags are rejected.
    """

    __tablename__ = "platform_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_platform_settings_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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

    updated_by: Mapped[User | None] = relationship("User", foreign_keys=[updated_by_user_id])

    def __repr__(self) -> str:
        return f"<PlatformSetting key={self.key}>"


class ToolConfiguration(Base):
    """Persistent admin overrides for registered server-side tools."""

    __tablename__ = "tool_configurations"
    __table_args__ = (UniqueConstraint("tool_name", name="uq_tool_configurations_tool_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    timeout_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmation_required_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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

    updated_by: Mapped[User | None] = relationship("User", foreign_keys=[updated_by_user_id])

    def __repr__(self) -> str:
        return f"<ToolConfiguration tool={self.tool_name} enabled={self.enabled}>"


class AdminAuditEvent(Base):
    """Append-only administrative action audit trail."""

    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_events_created_at", "created_at"),
        Index("ix_admin_audit_events_actor_user_id", "actor_user_id"),
        Index("ix_admin_audit_events_action", "action"),
        Index("ix_admin_audit_events_target_type", "target_type"),
        Index("ix_admin_audit_events_target_user_id", "target_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    safe_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    actor: Mapped[User | None] = relationship("User", foreign_keys=[actor_user_id])
    target_user: Mapped[User | None] = relationship("User", foreign_keys=[target_user_id])

    def __repr__(self) -> str:
        return f"<AdminAuditEvent action={self.action} target={self.target_type}>"
