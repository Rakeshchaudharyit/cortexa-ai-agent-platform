"""Phase 4 migration / schema presence tests."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_pgvector_extension_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    )
    row = result.first()
    assert row is not None
    assert row[0] == "vector"


@pytest.mark.asyncio
async def test_documents_tables_and_indexes(db_session: AsyncSession) -> None:
    tables = await db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('documents', 'document_chunks')
            ORDER BY table_name
            """
        )
    )
    names = {row[0] for row in tables.fetchall()}
    assert names == {"document_chunks", "documents"}

    columns = await db_session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'documents'
            """
        )
    )
    document_columns = {row[0] for row in columns.fetchall()}
    for required in (
        "id",
        "user_id",
        "original_filename",
        "checksum_sha256",
        "storage_key",
        "status",
        "chunk_count",
    ):
        assert required in document_columns

    chunk_columns = await db_session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'document_chunks'
            """
        )
    )
    chunk_names = {row[0] for row in chunk_columns.fetchall()}
    assert "embedding" in chunk_names
    assert "content" in chunk_names

    indexes = await db_session.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('documents', 'document_chunks')
            """
        )
    )
    index_names = {row[0] for row in indexes.fetchall()}
    assert "ix_documents_user_id" in index_names
    assert "ix_documents_status" in index_names
    # HNSW cosine index from migration 0003
    assert any("embedding" in name or "hnsw" in name.lower() for name in index_names)


@pytest.mark.asyncio
async def test_document_status_enum_exists(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            """
            SELECT t.typname
            FROM pg_type t
            WHERE t.typname = 'document_status'
            """
        )
    )
    assert result.first() is not None
