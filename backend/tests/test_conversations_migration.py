"""Phase 5 conversations migration / schema presence tests."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_conversation_tables_exist(db_session: AsyncSession) -> None:
    tables = await db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('conversations', 'messages', 'message_citations')
            ORDER BY table_name
            """
        )
    )
    names = {row[0] for row in tables.fetchall()}
    assert names == {"conversations", "message_citations", "messages"}


@pytest.mark.asyncio
async def test_conversation_enums_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            """
            SELECT t.typname
            FROM pg_type t
            WHERE t.typname IN (
                'conversation_status',
                'message_role',
                'message_status'
            )
            ORDER BY t.typname
            """
        )
    )
    names = {row[0] for row in result.fetchall()}
    assert names == {"conversation_status", "message_role", "message_status"}


@pytest.mark.asyncio
async def test_alembic_at_phase8_head(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))
    row = result.first()
    assert row is not None
    assert row[0] == "0009_enterprise_admin"
