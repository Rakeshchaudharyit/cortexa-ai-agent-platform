"""Phase 5 conversations — persistent chat, messages, and citations.

Revision ID: 0004_phase5_conversations
Revises: 0003_phase4_rag
Create Date: 2026-07-29

Notes:
- Conversation memory is scoped to a single conversation owned by one user.
- Message sequence numbers are unique per conversation and assigned server-side.
- Citation document/chunk FKs use SET NULL so historical answers survive deletes.
- client_request_id uniqueness is per (user, conversation) for lightweight idempotency.

Enum safety:
- Types are created with checkfirst=True before tables reference them.
- Column ENUM objects use create_type=False so SQLAlchemy does not double-CREATE.
- Downgrade drops tables first, then drops enum types with checkfirst=True.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase5_conversations"
down_revision: str | None = "0003_phase4_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

conversation_status_enum = postgresql.ENUM(
    "active",
    "archived",
    name="conversation_status",
    create_type=False,
)

message_role_enum = postgresql.ENUM(
    "user",
    "assistant",
    "system",
    name="message_role",
    create_type=False,
)

message_status_enum = postgresql.ENUM(
    "pending",
    "complete",
    "failed",
    "cancelled",
    name="message_status",
    create_type=False,
)


def _create_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "active",
        "archived",
        name="conversation_status",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "user",
        "assistant",
        "system",
        name="message_role",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "pending",
        "complete",
        "failed",
        "cancelled",
        name="message_status",
    ).create(bind, checkfirst=True)


def _drop_enums() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "pending",
        "complete",
        "failed",
        "cancelled",
        name="message_status",
    ).drop(bind, checkfirst=True)
    postgresql.ENUM(
        "user",
        "assistant",
        "system",
        name="message_role",
    ).drop(bind, checkfirst=True)
    postgresql.ENUM(
        "active",
        "archived",
        name="conversation_status",
    ).drop(bind, checkfirst=True)


def upgrade() -> None:
    _create_enums()

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "title",
            sa.String(length=200),
            server_default="New conversation",
            nullable=False,
        ),
        sa.Column("title_is_auto", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "status",
            conversation_status_enum,
            server_default="active",
            nullable=False,
        ),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("default_document_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_user_id_last_message_at",
        "conversations",
        ["user_id", "last_message_at"],
    )
    op.create_index(
        "ix_conversations_user_id_status",
        "conversations",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_conversations_user_id_updated_at",
        "conversations",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", message_role_enum, nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            message_status_enum,
            server_default="complete",
            nullable=False,
        ),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("finish_reason", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("regenerated_from_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("edited_from_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["regenerated_from_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["edited_from_message_id"],
            ["messages.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_messages_conversation_sequence",
        ),
        sa.UniqueConstraint(
            "user_id",
            "conversation_id",
            "client_request_id",
            name="uq_messages_user_conversation_client_request",
        ),
    )
    op.create_index(
        "ix_messages_conversation_id_sequence_number",
        "messages",
        ["conversation_id", "sequence_number"],
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index(
        "ix_messages_conversation_id_is_active",
        "messages",
        ["conversation_id", "is_active"],
    )

    op.create_table(
        "message_citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("citation_index", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.String(length=2000), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            "citation_index",
            name="uq_message_citations_message_index",
        ),
    )
    op.create_index(
        "ix_message_citations_message_id_citation_index",
        "message_citations",
        ["message_id", "citation_index"],
    )
    op.create_index("ix_message_citations_user_id", "message_citations", ["user_id"])
    op.create_index(
        "ix_message_citations_conversation_id",
        "message_citations",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_message_citations_conversation_id",
        table_name="message_citations",
    )
    op.drop_index("ix_message_citations_user_id", table_name="message_citations")
    op.drop_index(
        "ix_message_citations_message_id_citation_index",
        table_name="message_citations",
    )
    op.drop_table("message_citations")

    op.drop_index("ix_messages_conversation_id_is_active", table_name="messages")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_index("ix_messages_conversation_id_sequence_number", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_conversations_user_id_updated_at", table_name="conversations")
    op.drop_index("ix_conversations_user_id_status", table_name="conversations")
    op.drop_index("ix_conversations_user_id_last_message_at", table_name="conversations")
    op.drop_table("conversations")

    _drop_enums()
