"""Hard safety guards for destructive test database / Redis operations.

TESTING=true is intentionally insufficient. Every cleanup path must verify the
live connection targets an isolated test database and test identity.
"""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

FORBIDDEN_DATABASES = frozenset({"cortexa_agent", "postgres", "template0", "template1"})
FORBIDDEN_IDENTITIES = frozenset(
    {
        "cortexa-agent-development",
        "cortexa-agent-production",
        "cortexa-agent-staging",
    }
)
DEFAULT_TEST_IDENTITY = "cortexa-agent-test"
DEFAULT_TEST_DATABASE_SUFFIX = "_test"


class UnsafeTestTargetError(RuntimeError):
    """Raised when a destructive test operation would touch a non-test resource."""


def _require_test_database_name(database_name: str) -> None:
    name = (database_name or "").strip()
    if not name:
        raise UnsafeTestTargetError("Refusing destructive test action: empty database name")
    if name in FORBIDDEN_DATABASES:
        raise UnsafeTestTargetError(
            f"Refusing destructive test action against forbidden database '{name}'"
        )
    if name == "cortexa_agent":
        raise UnsafeTestTargetError(
            "Refusing destructive test action against development database 'cortexa_agent'"
        )
    if not name.endswith(DEFAULT_TEST_DATABASE_SUFFIX):
        raise UnsafeTestTargetError(
            f"Refusing destructive test action: database '{name}' must end with "
            f"'{DEFAULT_TEST_DATABASE_SUFFIX}'"
        )


def _require_test_identity(identity: str | None, *, expected_identity: str) -> None:
    if identity is None:
        raise UnsafeTestTargetError(
            "Refusing destructive test action: database identity metadata missing"
        )
    if identity in FORBIDDEN_IDENTITIES:
        raise UnsafeTestTargetError(
            f"Refusing destructive test action against forbidden identity '{identity}'"
        )
    if identity != expected_identity:
        raise UnsafeTestTargetError(
            f"Refusing destructive test action: identity '{identity}' != '{expected_identity}'"
        )


def assert_database_url_is_safe_for_tests(database_url: str | None) -> str:
    """Parse DATABASE_URL and refuse development/production database names."""
    if not database_url:
        raise UnsafeTestTargetError("Refusing destructive test action: DATABASE_URL is unset")
    parsed = urlparse(database_url)
    # Path is "/cortexa_agent_test" for postgresql URLs.
    db_name = (parsed.path or "").lstrip("/")
    if not db_name:
        raise UnsafeTestTargetError(
            "Refusing destructive test action: DATABASE_URL has no database name"
        )
    _require_test_database_name(db_name)
    return db_name


def _redis_db_index(parsed_path: str) -> int:
    if not parsed_path or parsed_path == "/":
        return 0
    try:
        return int(parsed_path.lstrip("/"))
    except ValueError as exc:
        raise UnsafeTestTargetError(
            f"Refusing destructive Redis test action: invalid Redis DB path '{parsed_path}'"
        ) from exc


def assert_redis_url_is_safe_for_tests(redis_url: str | None) -> None:
    """Refuse development Redis endpoints for test cleanup paths."""
    if not redis_url:
        raise UnsafeTestTargetError("Refusing destructive Redis test action: REDIS_URL is unset")
    parsed = urlparse(redis_url)
    host = (parsed.hostname or "").lower()
    db_index = _redis_db_index(parsed.path or "")

    if not host:
        raise UnsafeTestTargetError("Refusing destructive Redis test action: Redis host is empty")
    if "production" in host:
        raise UnsafeTestTargetError(f"Refusing destructive Redis test action against host '{host}'")
    if host == "redis":
        raise UnsafeTestTargetError(
            "Refusing destructive Redis test action against development host 'redis'"
        )
    if host == "redis-test":
        return
    # Host-side pytest against a published redis-test port must not use DB 0
    # (same default as development Redis on 16379).
    if host in {"localhost", "127.0.0.1"} and db_index == 0:
        raise UnsafeTestTargetError(
            "Refusing destructive Redis test action against localhost Redis DB 0 "
            "(development collision risk). Use host redis-test or a non-zero test DB index."
        )


def refuse_redis_flushall() -> None:
    """Explicit ban for FLUSHALL / FLUSHDB in test cleanup."""
    raise UnsafeTestTargetError(
        "Refusing Redis FLUSHALL/FLUSHDB: tests must never wipe shared Redis state"
    )


async def assert_safe_test_database(
    engine: AsyncEngine,
    *,
    expected_identity: str = DEFAULT_TEST_IDENTITY,
) -> str:
    """Query the live connection and refuse unsafe targets before cleanup.

    Returns the verified database name.
    """
    async with engine.connect() as connection:
        database_name = (await connection.execute(text("SELECT current_database()"))).scalar_one()
        _require_test_database_name(str(database_name))

        table_exists = (
            await connection.execute(
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
        ).scalar_one()
        if not bool(table_exists):
            raise UnsafeTestTargetError(
                "Refusing destructive test action: application_metadata table missing "
                "(migrate the test database first)"
            )

        identity = (
            await connection.execute(
                text(
                    """
                    SELECT value
                    FROM application_metadata
                    WHERE key = 'database_identity'
                    """
                )
            )
        ).scalar_one_or_none()
        _require_test_identity(identity, expected_identity=expected_identity)

    return str(database_name)


async def assert_safe_test_session(
    session: AsyncSession,
    *,
    expected_identity: str = DEFAULT_TEST_IDENTITY,
) -> str:
    """Same checks as assert_safe_test_database, using an open session."""
    database_name = (await session.execute(text("SELECT current_database()"))).scalar_one()
    _require_test_database_name(str(database_name))

    table_exists = (
        await session.execute(
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
    ).scalar_one()
    if not bool(table_exists):
        raise UnsafeTestTargetError(
            "Refusing destructive test action: application_metadata table missing "
            "(migrate the test database first)"
        )

    identity = (
        await session.execute(
            text(
                """
                SELECT value
                FROM application_metadata
                WHERE key = 'database_identity'
                """
            )
        )
    ).scalar_one_or_none()
    _require_test_identity(identity, expected_identity=expected_identity)
    return str(database_name)
