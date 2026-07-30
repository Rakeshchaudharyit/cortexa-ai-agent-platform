"""Database identity verification for readiness and ops tooling."""

from __future__ import annotations

import logging

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

logger = logging.getLogger("cortexa.db.identity")

REQUIRED_IDENTITY_KEYS: tuple[str, ...] = (
    "application_id",
    "database_identity",
)


async def check_database_identity(
    engine: AsyncEngine,
    settings: Settings,
) -> tuple[bool, str | None]:
    """Verify stored identity matches expected configuration.

    Returns (ok, sanitized_message_on_failure). Never includes connection
    strings, hostnames, or raw exception text.
    """
    if not settings.database_identity_check_enabled:
        return True, None

    try:
        async with engine.connect() as connection:
            table_exists = await connection.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.tables
                      WHERE table_schema = 'public'
                        AND table_name = 'application_metadata'
                    )
                    """
                )
            )
            if not bool(table_exists.scalar_one()):
                return False, "Database identity missing"

            result = await connection.execute(
                text(
                    """
                    SELECT key, value
                    FROM application_metadata
                    WHERE key IN :keys
                    """
                ).bindparams(bindparam("keys", expanding=True)),
                {"keys": list(REQUIRED_IDENTITY_KEYS)},
            )
            found = {row[0]: row[1] for row in result.fetchall()}
    except Exception:
        logger.exception("database_identity_check_failed")
        return False, "Database unavailable"

    for key in REQUIRED_IDENTITY_KEYS:
        if key not in found:
            return False, "Database identity missing"

    if found["application_id"] != settings.expected_application_id:
        return False, "Database identity mismatch"
    if found["database_identity"] != settings.expected_database_identity:
        return False, "Database identity mismatch"
    return True, None
