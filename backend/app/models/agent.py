"""Multi-agent orchestration persistence models (Phase 9)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AgentApprovalStatus,
    AgentExecutionMode,
    AgentRunStatus,
    AgentTaskStatus,
)

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User


def _enum_values(enum_cls: type[Enum]) -> list[str]:
    return [str(item.value) for item in enum_cls]


class AgentDefinition(Base):
    """Server-managed specialist agent definition (seeded; not model-created)."""

    __tablename__ = "agent_definitions"
    __table_args__ = (
        UniqueConstraint("key", name="uq_agent_definitions_key"),
        Index("ix_agent_definitions_key_enabled", "key", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    system_managed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    capabilities_json: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    allowed_tools_json: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    maximum_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
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

    def __repr__(self) -> str:
        return f"<AgentDefinition key={self.key} enabled={self.enabled}>"


class AgentRun(Base):
    """Owned multi-agent (or classified single-agent) execution record."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_user_status_created", "user_id", "status", "created_at"),
        Index("ix_agent_runs_conversation_id", "conversation_id"),
        Index("ix_agent_runs_correlation_id", "correlation_id"),
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
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    coordinator_agent_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="coordinator",
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(
            AgentRunStatus,
            name="agent_run_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=AgentRunStatus.pending,
        server_default=AgentRunStatus.pending.value,
    )
    execution_mode: Mapped[AgentExecutionMode] = mapped_column(
        SAEnum(
            AgentExecutionMode,
            name="agent_execution_mode",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=AgentExecutionMode.single_agent,
        server_default=AgentExecutionMode.single_agent.value,
    )
    original_request_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    safe_plan_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    steps_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    llm_calls_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tool_calls_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
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

    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
    conversation: Mapped[Conversation | None] = relationship(
        "Conversation",
        foreign_keys=[conversation_id],
    )
    tasks: Mapped[list[AgentTask]] = relationship(
        "AgentTask",
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="AgentTask.sequence",
    )
    handoffs: Mapped[list[AgentHandoff]] = relationship(
        "AgentHandoff",
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )
    approvals: Mapped[list[AgentApproval]] = relationship(
        "AgentApproval",
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[AgentRunEvent]] = relationship(
        "AgentRunEvent",
        back_populates="agent_run",
        cascade="all, delete-orphan",
        order_by="AgentRunEvent.created_at",
    )

    def __repr__(self) -> str:
        return f"<AgentRun id={self.id} status={self.status}>"


class AgentTask(Base):
    """Single bounded task assigned to a registered specialist agent."""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_run_status_sequence", "agent_run_id", "status", "sequence"),
        Index("ix_agent_tasks_parent_task_id", "parent_task_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    objective: Mapped[str] = mapped_column(String(1000), nullable=False)
    safe_input_summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[AgentTaskStatus] = mapped_column(
        SAEnum(
            AgentTaskStatus,
            name="agent_task_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=AgentTaskStatus.pending,
        server_default=AgentTaskStatus.pending.value,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    dependencies_json: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    allowed_tools_json: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    maximum_retries: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    result_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
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

    agent_run: Mapped[AgentRun] = relationship("AgentRun", back_populates="tasks")
    parent_task: Mapped[AgentTask | None] = relationship(
        "AgentTask",
        remote_side="AgentTask.id",
        foreign_keys=[parent_task_id],
    )

    def __repr__(self) -> str:
        return (
            f"<AgentTask id={self.id} agent={self.assigned_agent_key} "
            f"seq={self.sequence} status={self.status}>"
        )


class AgentHandoff(Base):
    """Audited handoff between registered agents within a run."""

    __tablename__ = "agent_handoffs"
    __table_args__ = (Index("ix_agent_handoffs_run_created", "agent_run_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    from_agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    to_agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    safe_context_summary: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    agent_run: Mapped[AgentRun] = relationship("AgentRun", back_populates="handoffs")

    def __repr__(self) -> str:
        return f"<AgentHandoff {self.from_agent_key}->{self.to_agent_key}>"


class AgentApproval(Base):
    """User approval gate for persistent write actions during a run."""

    __tablename__ = "agent_approvals"
    __table_args__ = (
        Index("ix_agent_approvals_user_status", "user_id", "status"),
        Index("ix_agent_approvals_run_id", "agent_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AgentApprovalStatus] = mapped_column(
        SAEnum(
            AgentApprovalStatus,
            name="agent_approval_status",
            values_callable=_enum_values,
        ),
        nullable=False,
        default=AgentApprovalStatus.pending,
        server_default=AgentApprovalStatus.pending.value,
    )
    safe_action_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
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

    agent_run: Mapped[AgentRun] = relationship("AgentRun", back_populates="approvals")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<AgentApproval id={self.id} status={self.status}>"


class AgentRunEvent(Base):
    """Append-only safe timeline events for an agent run (no hidden reasoning)."""

    __tablename__ = "agent_run_events"
    __table_args__ = (Index("ix_agent_run_events_run_created", "agent_run_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    agent_run: Mapped[AgentRun] = relationship("AgentRun", back_populates="events")

    def __repr__(self) -> str:
        return f"<AgentRunEvent type={self.event_type} run={self.agent_run_id}>"
