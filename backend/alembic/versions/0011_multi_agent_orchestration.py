"""Phase 9 multi-agent orchestration tables.

Revision ID: 0011_multi_agent_orchestration
Revises: 0010_admin_deletion_controls
Create Date: 2026-08-01

Notes:
- Seeds system-managed agent definitions (coordinator, planning, conversation,
  knowledge, memory, tool, safety).
- Persists agent runs, tasks, handoffs, approvals, and safe timeline events.
- Does not weaken ownership, tool gating, memory confirmation, or deletion controls.
- Does not store hidden chain-of-thought or full prompts.

Enum safety:
- Types are created with checkfirst=True before tables reference them.
- Column ENUM objects use create_type=False so SQLAlchemy does not double-CREATE.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_multi_agent_orchestration"
down_revision: str | None = "0010_admin_deletion_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

agent_run_status_enum = postgresql.ENUM(
    "pending",
    "planning",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "timed_out",
    name="agent_run_status",
    create_type=False,
)

agent_task_status_enum = postgresql.ENUM(
    "pending",
    "ready",
    "running",
    "awaiting_approval",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
    "timed_out",
    name="agent_task_status",
    create_type=False,
)

agent_approval_status_enum = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    "expired",
    "cancelled",
    name="agent_approval_status",
    create_type=False,
)

agent_execution_mode_enum = postgresql.ENUM(
    "single_agent",
    "multi_agent",
    name="agent_execution_mode",
    create_type=False,
)

_SYSTEM_AGENTS: list[dict[str, object]] = [
    {
        "key": "coordinator",
        "display_name": "Coordinator Agent",
        "description": (
            "Owns each execution: classifies complexity, validates plans, "
            "dispatches tasks, enforces limits, and produces the final response."
        ),
        "capabilities": [
            "classify",
            "dispatch",
            "enforce_limits",
            "combine_results",
            "cancel",
        ],
        "allowed_tools": [],
        "maximum_steps": 12,
        "timeout_seconds": 120,
    },
    {
        "key": "planning",
        "display_name": "Planning Agent",
        "description": (
            "Decomposes complex requests into structured task plans using "
            "registered agent names only. Never executes tools or writes data."
        ),
        "capabilities": ["decompose", "structure_plan", "identify_approvals"],
        "allowed_tools": [],
        "maximum_steps": 2,
        "timeout_seconds": 45,
    },
    {
        "key": "conversation",
        "display_name": "Conversation Agent",
        "description": (
            "Handles normal chat, synthesizes final responses, and remains "
            "the fallback for simple requests."
        ),
        "capabilities": ["chat", "synthesize", "fallback"],
        "allowed_tools": [],
        "maximum_steps": 4,
        "timeout_seconds": 60,
    },
    {
        "key": "knowledge",
        "display_name": "Knowledge Agent",
        "description": (
            "Retrieves user-authorized document context, validates citations, "
            "and summarizes retrieved passages. Never writes memories."
        ),
        "capabilities": ["retrieve_documents", "cite", "summarize_context"],
        "allowed_tools": ["knowledge_search"],
        "maximum_steps": 4,
        "timeout_seconds": 45,
    },
    {
        "key": "memory",
        "display_name": "Memory Agent",
        "description": (
            "Retrieves approved memories and processes explicit remember, "
            "update, forget, or list requests via MemoryService."
        ),
        "capabilities": [
            "retrieve_memories",
            "explicit_memory_write",
            "list_memories",
        ],
        "allowed_tools": ["memory_list", "memory_search"],
        "maximum_steps": 4,
        "timeout_seconds": 45,
    },
    {
        "key": "tool",
        "display_name": "Tool Agent",
        "description": (
            "Executes registered and enabled tools through ToolExecutor with "
            "argument validation and execution audits."
        ),
        "capabilities": ["execute_tools", "validate_arguments"],
        "allowed_tools": [
            "calculator",
            "current_datetime",
            "conversation_summary",
        ],
        "maximum_steps": 4,
        "timeout_seconds": 45,
    },
    {
        "key": "safety",
        "display_name": "Safety Agent",
        "description": (
            "Validates plans, rejects unregistered agents and unauthorized "
            "tools, detects prompt-injection and policy bypass attempts, "
            "and requires approval for sensitive writes."
        ),
        "capabilities": [
            "validate_plan",
            "detect_injection",
            "require_approval",
            "reject_unauthorized",
        ],
        "allowed_tools": [],
        "maximum_steps": 2,
        "timeout_seconds": 30,
    },
]


def _create_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "pending",
        "planning",
        "running",
        "awaiting_approval",
        "completed",
        "failed",
        "cancelled",
        "timed_out",
        name="agent_run_status",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "pending",
        "ready",
        "running",
        "awaiting_approval",
        "succeeded",
        "failed",
        "skipped",
        "cancelled",
        "timed_out",
        name="agent_task_status",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "pending",
        "approved",
        "rejected",
        "expired",
        "cancelled",
        name="agent_approval_status",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "single_agent",
        "multi_agent",
        name="agent_execution_mode",
    ).create(bind, checkfirst=True)


def _drop_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(name="agent_execution_mode").drop(bind, checkfirst=True)
    postgresql.ENUM(name="agent_approval_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="agent_task_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="agent_run_status").drop(bind, checkfirst=True)


def upgrade() -> None:
    _create_enums()

    op.create_table(
        "agent_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("system_managed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "capabilities_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "allowed_tools_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("maximum_steps", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="45"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_agent_definitions_key"),
    )
    op.create_index(
        "ix_agent_definitions_key_enabled",
        "agent_definitions",
        ["key", "enabled"],
        unique=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "coordinator_agent_key",
            sa.String(length=64),
            nullable=False,
            server_default="coordinator",
        ),
        sa.Column(
            "status",
            agent_run_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "execution_mode",
            agent_execution_mode_enum,
            nullable=False,
            server_default="single_agent",
        ),
        sa.Column("original_request_summary", sa.String(length=500), nullable=False),
        sa.Column("safe_plan_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("maximum_steps", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("steps_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("safe_error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_runs_user_status_created",
        "agent_runs",
        ["user_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_conversation_id",
        "agent_runs",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_runs_correlation_id",
        "agent_runs",
        ["correlation_id"],
        unique=False,
    )

    op.create_table(
        "agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_agent_key", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.String(length=1000), nullable=False),
        sa.Column(
            "safe_input_summary",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "status",
            agent_task_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "dependencies_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "allowed_tools_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximum_retries", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_summary", sa.String(length=2000), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("safe_error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_tasks_run_status_sequence",
        "agent_tasks",
        ["agent_run_id", "status", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_agent_tasks_parent_task_id",
        "agent_tasks",
        ["parent_task_id"],
        unique=False,
    )

    op.create_table(
        "agent_handoffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_agent_key", sa.String(length=64), nullable=False),
        sa.Column("to_agent_key", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "safe_context_summary",
            sa.String(length=1000),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_handoffs_run_created",
        "agent_handoffs",
        ["agent_run_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            agent_approval_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("safe_action_summary", sa.String(length=500), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_approvals_user_status",
        "agent_approvals",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_agent_approvals_run_id",
        "agent_approvals",
        ["agent_run_id"],
        unique=False,
    )

    op.create_table(
        "agent_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=True),
        sa.Column("safe_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_run_events_run_created",
        "agent_run_events",
        ["agent_run_id", "created_at"],
        unique=False,
    )

    definitions = sa.table(
        "agent_definitions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("description", sa.Text),
        sa.column("version", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("system_managed", sa.Boolean),
        sa.column("capabilities_json", postgresql.JSONB),
        sa.column("allowed_tools_json", postgresql.JSONB),
        sa.column("maximum_steps", sa.Integer),
        sa.column("timeout_seconds", sa.Integer),
    )
    rows = []
    for agent in _SYSTEM_AGENTS:
        rows.append(
            {
                "id": uuid.uuid4(),
                "key": agent["key"],
                "display_name": agent["display_name"],
                "description": agent["description"],
                "version": "1.0.0",
                "enabled": True,
                "system_managed": True,
                "capabilities_json": agent["capabilities"],
                "allowed_tools_json": agent["allowed_tools"],
                "maximum_steps": agent["maximum_steps"],
                "timeout_seconds": agent["timeout_seconds"],
            }
        )
    op.bulk_insert(definitions, rows)


def downgrade() -> None:
    op.drop_index("ix_agent_run_events_run_created", table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.drop_index("ix_agent_approvals_run_id", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_user_status", table_name="agent_approvals")
    op.drop_table("agent_approvals")
    op.drop_index("ix_agent_handoffs_run_created", table_name="agent_handoffs")
    op.drop_table("agent_handoffs")
    op.drop_index("ix_agent_tasks_parent_task_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_run_status_sequence", table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_index("ix_agent_runs_correlation_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_conversation_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_status_created", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_agent_definitions_key_enabled", table_name="agent_definitions")
    op.drop_table("agent_definitions")
    _drop_enums()
