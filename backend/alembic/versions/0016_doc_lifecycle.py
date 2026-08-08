"""Enterprise knowledge lifecycle and version control.

Revision ID: 0016_doc_lifecycle
Revises: 0015_knowledge_mgmt
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_doc_lifecycle"
down_revision: str | None = "0015_knowledge_mgmt"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["active_version_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["folder_id"], ["document_folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_user_id", "knowledge_documents", ["user_id"])
    op.create_index("ix_knowledge_documents_folder_id", "knowledge_documents", ["folder_id"])

    op.add_column("documents", sa.Column("knowledge_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("lifecycle_state", sa.String(length=32), server_default="active", nullable=False))
    op.add_column("documents", sa.Column("is_active_version", sa.Boolean(), server_default=sa.text("true"), nullable=False))

    # Build one logical asset per root document and attach every descendant version.
    op.execute(
        """
        INSERT INTO knowledge_documents (id, user_id, folder_id, title, tags, created_at, updated_at)
        SELECT d.id, d.user_id, d.folder_id, COALESCE(d.title, d.original_filename), d.tags, d.created_at, d.updated_at
        FROM documents d
        WHERE d.supersedes_document_id IS NULL
        """
    )
    op.execute(
        """
        WITH RECURSIVE version_tree AS (
            SELECT d.id, d.id AS root_id
            FROM documents d
            WHERE d.supersedes_document_id IS NULL
            UNION ALL
            SELECT child.id, version_tree.root_id
            FROM documents child
            JOIN version_tree ON child.supersedes_document_id = version_tree.id
        )
        UPDATE documents d
        SET knowledge_document_id = version_tree.root_id
        FROM version_tree
        WHERE d.id = version_tree.id
        """
    )
    # Defensive backfill for any orphaned legacy rows.
    op.execute(
        """
        INSERT INTO knowledge_documents (id, user_id, folder_id, title, tags, created_at, updated_at)
        SELECT d.id, d.user_id, d.folder_id, COALESCE(d.title, d.original_filename), d.tags, d.created_at, d.updated_at
        FROM documents d
        WHERE d.knowledge_document_id IS NULL
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute("UPDATE documents SET knowledge_document_id = id WHERE knowledge_document_id IS NULL")

    op.create_foreign_key(
        "fk_documents_knowledge_document_id", "documents", "knowledge_documents",
        ["knowledge_document_id"], ["id"], ondelete="CASCADE"
    )
    op.alter_column("documents", "knowledge_document_id", nullable=False)
    op.create_index("ix_documents_knowledge_document_id", "documents", ["knowledge_document_id"])
    op.create_index("ix_documents_active_version", "documents", ["user_id", "is_active_version"])

    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (knowledge_document_id) id, knowledge_document_id
            FROM documents
            WHERE archived_at IS NULL AND status = 'ready'
            ORDER BY knowledge_document_id, version_number DESC, created_at DESC
        )
        UPDATE knowledge_documents k
        SET active_version_id = latest.id
        FROM latest
        WHERE k.id = latest.knowledge_document_id
        """
    )
    op.execute(
        """
        UPDATE knowledge_documents k
        SET title = COALESCE(d.title, d.original_filename),
            folder_id = d.folder_id,
            tags = d.tags,
            updated_at = d.updated_at
        FROM documents d
        WHERE k.active_version_id = d.id
        """
    )
    op.execute("UPDATE documents SET is_active_version = false")
    op.execute(
        """
        UPDATE documents d
        SET is_active_version = true
        FROM knowledge_documents k
        WHERE k.active_version_id = d.id
        """
    )
    op.execute(
        """
        UPDATE documents
        SET lifecycle_state = CASE
            WHEN archived_at IS NOT NULL THEN 'archived'
            WHEN status = 'failed' THEN 'failed'
            WHEN status IN ('pending', 'processing') THEN 'processing'
            WHEN is_active_version THEN 'active'
            ELSE 'superseded'
        END
        """
    )

    op.create_table(
        "knowledge_document_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["knowledge_document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_document_events_knowledge_id", "knowledge_document_events", ["knowledge_document_id"])
    op.create_index("ix_knowledge_document_events_created_at", "knowledge_document_events", ["created_at"])
    op.execute(
        """
        INSERT INTO knowledge_document_events
            (id, knowledge_document_id, document_id, actor_user_id, event_type, metadata, created_at)
        SELECT gen_random_uuid(), d.knowledge_document_id, d.id, d.user_id, 'version_migrated',
               jsonb_build_object('version_number', d.version_number, 'lifecycle_state', d.lifecycle_state), d.created_at
        FROM documents d
        """
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_document_events_created_at", table_name="knowledge_document_events")
    op.drop_index("ix_knowledge_document_events_knowledge_id", table_name="knowledge_document_events")
    op.drop_table("knowledge_document_events")
    op.drop_index("ix_documents_active_version", table_name="documents")
    op.drop_index("ix_documents_knowledge_document_id", table_name="documents")
    op.drop_constraint("fk_documents_knowledge_document_id", "documents", type_="foreignkey")
    op.drop_column("documents", "is_active_version")
    op.drop_column("documents", "lifecycle_state")
    op.drop_column("documents", "knowledge_document_id")
    op.drop_index("ix_knowledge_documents_folder_id", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_user_id", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
