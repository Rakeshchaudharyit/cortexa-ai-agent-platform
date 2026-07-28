"""Database connectivity checks."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("cortexa.db.health")


async def check_database(engine: AsyncEngine) -> tuple[bool, str | None]:
    """Run SELECT 1. Returns (ok, sanitized_message_on_failure)."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True, None
    except Exception:
        logger.exception("database_health_check_failed")
        return False, "Database unavailable"
