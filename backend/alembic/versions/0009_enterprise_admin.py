"""Phase 8 enterprise administration tables.

Revision ID: 0009_enterprise_admin
Revises: 0008_long_term_memory
Create Date: 2026-08-01

Notes:
- Adds platform_settings for safe DB-backed configuration overrides.
- Adds tool_configurations for persistent tool enable/disable overrides.
- Adds admin_audit_events for administrative action auditing.
- Does not alter existing user/document/conversation/memory ownership rules.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_enterprise_admin"
down_revision: str | None = "0008_long_term_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_platform_settings_key"),
    )
    op.create_index("ix_platform_settings_key", "platform_settings", ["key"], unique=False)

    op.create_table(
        "tool_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("timeout_override", sa.Integer(), nullable=True),
        sa.Column("confirmation_required_override", sa.Boolean(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tool_name", name="uq_tool_configurations_tool_name"),
    )
    op.create_index(
        "ix_tool_configurations_tool_name",
        "tool_configurations",
        ["tool_name"],
        unique=False,
    )

    op.create_table(
        "admin_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("safe_summary", sa.String(length=500), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_events_created_at",
        "admin_audit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_events_actor_user_id",
        "admin_audit_events",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_events_action",
        "admin_audit_events",
        ["action"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_events_target_type",
        "admin_audit_events",
        ["target_type"],
        unique=False,
    )
    op.create_index(
        "ix_admin_audit_events_target_user_id",
        "admin_audit_events",
        ["target_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_events_target_user_id", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_target_type", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_action", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_actor_user_id", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_events_created_at", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")

    op.drop_index("ix_tool_configurations_tool_name", table_name="tool_configurations")
    op.drop_table("tool_configurations")

    op.drop_index("ix_platform_settings_key", table_name="platform_settings")
    op.drop_table("platform_settings")
