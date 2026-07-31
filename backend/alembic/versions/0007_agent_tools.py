"""Phase 6 agent tool execution audit table.

Revision ID: 0007_agent_tools
Revises: 0006_database_identity
Create Date: 2026-07-30

Notes:
- Stores audited tool invocations with ownership and safe JSON payloads.
- Does not alter conversation ownership rules or Phase 5 message tables.

Enum safety:
- Type is created with checkfirst=True before the table references it.
- Column ENUM objects use create_type=False so SQLAlchemy does not double-CREATE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_agent_tools"
down_revision: str | None = "0006_database_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

tool_execution_status_enum = postgresql.ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    "denied",
    "timed_out",
    "cancelled",
    name="tool_execution_status",
    create_type=False,
)


def _create_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "pending",
        "running",
        "succeeded",
        "failed",
        "denied",
        "timed_out",
        "cancelled",
        name="tool_execution_status",
    ).create(bind, checkfirst=True)


def _drop_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(name="tool_execution_status").drop(bind, checkfirst=True)


def upgrade() -> None:
    _create_enums()
    op.create_table(
        "tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column(
            "status",
            tool_execution_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("arguments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
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
    )
    op.create_index(
        "ix_tool_executions_user_id_created_at",
        "tool_executions",
        ["user_id", "created_at"],
    )
    op.create_index("ix_tool_executions_conversation_id", "tool_executions", ["conversation_id"])
    op.create_index("ix_tool_executions_message_id", "tool_executions", ["message_id"])
    op.create_index("ix_tool_executions_tool_name", "tool_executions", ["tool_name"])
    op.create_index("ix_tool_executions_status", "tool_executions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tool_executions_status", table_name="tool_executions")
    op.drop_index("ix_tool_executions_tool_name", table_name="tool_executions")
    op.drop_index("ix_tool_executions_message_id", table_name="tool_executions")
    op.drop_index("ix_tool_executions_conversation_id", table_name="tool_executions")
    op.drop_index("ix_tool_executions_user_id_created_at", table_name="tool_executions")
    op.drop_table("tool_executions")
    _drop_enums()
