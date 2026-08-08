"""Enterprise knowledge management foundation.

Revision ID: 0015_knowledge_mgmt
Revises: 0014_message_feedback
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_knowledge_mgmt"
down_revision: str | None = "0014_message_feedback"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_document_folders_user_name"),
    )
    op.create_index("ix_document_folders_user_id", "document_folders", ["user_id"])

    op.drop_constraint("uq_documents_user_checksum", "documents", type_="unique")
    op.add_column("documents", sa.Column("folder_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column("documents", sa.Column("version_number", sa.Integer(), server_default="1", nullable=False))
    op.add_column("documents", sa.Column("supersedes_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_documents_folder_id", "documents", "document_folders", ["folder_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_documents_supersedes", "documents", "documents", ["supersedes_document_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_documents_folder_id", "documents", ["folder_id"])
    op.create_index("ix_documents_user_archived_at", "documents", ["user_id", "archived_at"])
    op.create_index("ix_documents_user_checksum", "documents", ["user_id", "checksum_sha256"])
    op.execute("UPDATE documents SET title = original_filename WHERE title IS NULL")


def downgrade() -> None:
    op.drop_index("ix_documents_user_checksum", table_name="documents")
    op.drop_index("ix_documents_user_archived_at", table_name="documents")
    op.drop_index("ix_documents_folder_id", table_name="documents")
    op.drop_constraint("fk_documents_supersedes", "documents", type_="foreignkey")
    op.drop_constraint("fk_documents_folder_id", "documents", type_="foreignkey")
    op.drop_column("documents", "archived_at")
    op.drop_column("documents", "supersedes_document_id")
    op.drop_column("documents", "version_number")
    op.drop_column("documents", "tags")
    op.drop_column("documents", "title")
    op.drop_column("documents", "folder_id")
    op.create_unique_constraint("uq_documents_user_checksum", "documents", ["user_id", "checksum_sha256"])
    op.drop_index("ix_document_folders_user_id", table_name="document_folders")
    op.drop_table("document_folders")
