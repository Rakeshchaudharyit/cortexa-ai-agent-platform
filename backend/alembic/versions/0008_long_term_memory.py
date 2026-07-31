"""Phase 7 long-term memory tables and conversation memory controls.

Revision ID: 0008_long_term_memory
Revises: 0007_agent_tools
Create Date: 2026-07-31

Notes:
- Adds user_memories, user_memory_settings, and memory_audit_events.
- Adds optional per-conversation memory override columns.
- Soft-delete + content redaction supported at the application layer.
- Embeddings reuse the existing 768-dimension pgvector layout.

Enum safety:
- Types are created with checkfirst=True before tables reference them.
- Column ENUM objects use create_type=False so SQLAlchemy does not double-CREATE.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from app.models.document import EMBEDDING_DIMENSION
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0008_long_term_memory"
down_revision: str | None = "0007_agent_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

memory_category_enum = postgresql.ENUM(
    "preference",
    "personal_context",
    "project",
    "instruction",
    "workflow",
    "technical_context",
    "decision",
    "goal",
    "relationship_context",
    "other",
    name="memory_category",
    create_type=False,
)

memory_source_enum = postgresql.ENUM(
    "explicit_user_request",
    "assistant_suggestion",
    "automatic_extraction",
    "imported",
    "system_generated",
    name="memory_source",
    create_type=False,
)

memory_status_enum = postgresql.ENUM(
    "proposed",
    "active",
    "archived",
    "rejected",
    "deleted",
    name="memory_status",
    create_type=False,
)

memory_confidence_enum = postgresql.ENUM(
    "high",
    "medium",
    "low",
    name="memory_confidence",
    create_type=False,
)

memory_audit_event_type_enum = postgresql.ENUM(
    "proposed",
    "created",
    "confirmed",
    "updated",
    "retrieved",
    "injected",
    "archived",
    "restored",
    "rejected",
    "deleted",
    "expired",
    "conflict_superseded",
    name="memory_audit_event_type",
    create_type=False,
)


def _create_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "preference",
        "personal_context",
        "project",
        "instruction",
        "workflow",
        "technical_context",
        "decision",
        "goal",
        "relationship_context",
        "other",
        name="memory_category",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "explicit_user_request",
        "assistant_suggestion",
        "automatic_extraction",
        "imported",
        "system_generated",
        name="memory_source",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "proposed",
        "active",
        "archived",
        "rejected",
        "deleted",
        name="memory_status",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "high",
        "medium",
        "low",
        name="memory_confidence",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "proposed",
        "created",
        "confirmed",
        "updated",
        "retrieved",
        "injected",
        "archived",
        "restored",
        "rejected",
        "deleted",
        "expired",
        "conflict_superseded",
        name="memory_audit_event_type",
    ).create(bind, checkfirst=True)


def _drop_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(name="memory_audit_event_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="memory_confidence").drop(bind, checkfirst=True)
    postgresql.ENUM(name="memory_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="memory_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="memory_category").drop(bind, checkfirst=True)


def upgrade() -> None:
    _create_enums()

    op.create_table(
        "user_memory_settings",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "automatic_extraction_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "suggestions_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "require_confirmation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "include_memories_in_chat",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "maximum_active_memories",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
        sa.Column("default_expiration_days", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("user_id", name="uq_user_memory_settings_user_id"),
    )

    op.create_table(
        "user_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category",
            memory_category_enum,
            nullable=False,
            server_default="other",
        ),
        sa.Column(
            "status",
            memory_status_enum,
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.String(length=2000), nullable=False),
        sa.Column(
            "source",
            memory_source_enum,
            nullable=False,
            server_default="explicit_user_request",
        ),
        sa.Column(
            "source_conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confidence", memory_confidence_enum, nullable=True),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "confirmation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column(
            "superseded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_user_memories_user_id_status",
        "user_memories",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_user_memories_user_id_category",
        "user_memories",
        ["user_id", "category"],
    )
    op.create_index(
        "ix_user_memories_user_id_updated_at",
        "user_memories",
        ["user_id", "updated_at"],
    )
    op.create_index(
        "ix_user_memories_user_id_last_used_at",
        "user_memories",
        ["user_id", "last_used_at"],
    )
    op.create_index(
        "ix_user_memories_normalized_content",
        "user_memories",
        ["user_id", "normalized_content"],
    )

    op.create_table(
        "memory_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_memories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", memory_audit_event_type_enum, nullable=False),
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
        sa.Column(
            "safe_metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_memory_audit_events_user_id_created_at",
        "memory_audit_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_memory_audit_events_memory_id",
        "memory_audit_events",
        ["memory_id"],
    )
    op.create_index(
        "ix_memory_audit_events_event_type",
        "memory_audit_events",
        ["event_type"],
    )

    op.add_column(
        "conversations",
        sa.Column("memory_enabled_override", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "memory_context_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("memory_disabled_reason", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "memory_disabled_reason")
    op.drop_column("conversations", "memory_context_used")
    op.drop_column("conversations", "memory_enabled_override")

    op.drop_index("ix_memory_audit_events_event_type", table_name="memory_audit_events")
    op.drop_index("ix_memory_audit_events_memory_id", table_name="memory_audit_events")
    op.drop_index(
        "ix_memory_audit_events_user_id_created_at",
        table_name="memory_audit_events",
    )
    op.drop_table("memory_audit_events")

    op.drop_index("ix_user_memories_normalized_content", table_name="user_memories")
    op.drop_index("ix_user_memories_user_id_last_used_at", table_name="user_memories")
    op.drop_index("ix_user_memories_user_id_updated_at", table_name="user_memories")
    op.drop_index("ix_user_memories_user_id_category", table_name="user_memories")
    op.drop_index("ix_user_memories_user_id_status", table_name="user_memories")
    op.drop_table("user_memories")
    op.drop_table("user_memory_settings")
    _drop_enums()
