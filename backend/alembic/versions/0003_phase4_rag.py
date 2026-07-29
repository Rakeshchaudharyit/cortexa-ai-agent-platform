"""Phase 4 RAG foundation — pgvector, documents, and chunks.

Revision ID: 0003_phase4_rag
Revises: 0002_phase3_auth
Create Date: 2026-07-29

Notes:
- Enables the pgvector extension (requires a Postgres image that ships pgvector).
- Embedding column dimension is fixed at 768 for nomic-embed-text.
- An HNSW cosine index is created for semantic retrieval. HNSW is preferred over
  IVFFlat here because it needs no training step, works well from an empty table,
  and is suitable for local/dev corpus sizes without tuning lists/probes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase4_rag"
down_revision: str | None = "0002_phase3_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

document_status_enum = postgresql.ENUM(
    "pending",
    "processing",
    "ready",
    "failed",
    name="document_status",
    create_type=False,
)

EMBEDDING_DIMENSION = 768


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    bind = op.get_bind()
    postgresql.ENUM(
        "pending",
        "processing",
        "ready",
        "failed",
        name="document_status",
    ).create(bind, checkfirst=True)

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            document_status_enum,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("character_count", sa.Integer(), server_default="0", nullable=False),
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
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "checksum_sha256", name="uq_documents_user_checksum"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_checksum_sha256", "documents", ["checksum_sha256"])
    op.create_index("ix_documents_user_created_at", "documents", ["user_id", "created_at"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_index",
        ),
    )
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index(
        "ix_document_chunks_document_chunk_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    # Cosine HNSW for semantic retrieval (see module docstring).
    op.execute(
        sa.text(
            "CREATE INDEX ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw"))
    op.drop_index("ix_document_chunks_document_chunk_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_user_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_documents_user_created_at", table_name="documents")
    op.drop_index("ix_documents_checksum_sha256", table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_table("documents")

    bind = op.get_bind()
    postgresql.ENUM(name="document_status").drop(bind, checkfirst=True)

    # Leave the vector extension installed — other databases may depend on it.
    # Downgrade does not DROP EXTENSION vector.
