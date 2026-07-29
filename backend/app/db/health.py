"""Database connectivity and schema readiness checks."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("cortexa.db.health")

# Phase 5 conversation persistence — required for chat API readiness.
REQUIRED_CONVERSATION_TABLES: tuple[str, ...] = (
    "conversations",
    "messages",
    "message_citations",
)


def _alembic_config() -> Config:
    """Locate alembic.ini relative to the installed app package or /app."""
    candidates = (
        Path("/app/alembic.ini"),
        Path(__file__).resolve().parents[2] / "alembic.ini",
    )
    for path in candidates:
        if path.is_file():
            cfg = Config(str(path))
            script_location = path.parent / "alembic"
            if script_location.is_dir():
                cfg.set_main_option("script_location", str(script_location))
            return cfg
    raise FileNotFoundError("alembic.ini not found")


def _head_revisions() -> set[str]:
    script = ScriptDirectory.from_config(_alembic_config())
    return set(script.get_heads())


def _check_migration_head(connection: Connection) -> tuple[bool, str | None]:
    context = MigrationContext.configure(connection)
    current = context.get_current_revision()
    heads = _head_revisions()
    if current is None:
        return False, "Database migrations incomplete"
    if current not in heads:
        return False, "Database migrations incomplete"
    return True, None


async def check_required_tables(engine: AsyncEngine) -> tuple[bool, str | None]:
    """Verify Phase 5 conversation tables exist."""
    try:
        async with engine.connect() as connection:
            stmt = text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN :tables
                """
            ).bindparams(bindparam("tables", expanding=True))
            result = await connection.execute(
                stmt,
                {"tables": list(REQUIRED_CONVERSATION_TABLES)},
            )
            found = {row[0] for row in result.fetchall()}
        missing = [name for name in REQUIRED_CONVERSATION_TABLES if name not in found]
        if missing:
            return False, "Database schema incomplete"
        return True, None
    except Exception:
        logger.exception("database_schema_check_failed")
        return False, "Database unavailable"


async def check_migrations(engine: AsyncEngine) -> tuple[bool, str | None]:
    """Verify Alembic revision matches head."""
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_check_migration_head)
    except Exception:
        logger.exception("database_migration_check_failed")
        return False, "Database unavailable"


async def check_database(engine: AsyncEngine) -> tuple[bool, str | None]:
    """Connectivity + migration head + required Phase 5 tables.

    Returns (ok, sanitized_message_on_failure). Never includes hostnames,
    connection strings, or raw exception text.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        logger.exception("database_health_check_failed")
        return False, "Database unavailable"

    migrations_ok, migrations_message = await check_migrations(engine)
    if not migrations_ok:
        return False, migrations_message or "Database migrations incomplete"

    tables_ok, tables_message = await check_required_tables(engine)
    if not tables_ok:
        return False, tables_message or "Database schema incomplete"

    return True, None
