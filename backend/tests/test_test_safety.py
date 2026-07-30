"""Hard guards: destructive test cleanup must never touch development DB/Redis."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.db.test_safety import (
    UnsafeTestTargetError,
    assert_database_url_is_safe_for_tests,
    assert_redis_url_is_safe_for_tests,
    assert_safe_test_session,
    refuse_redis_flushall,
)
from sqlalchemy.ext.asyncio import AsyncSession


def test_database_url_rejects_development_cortexa_agent() -> None:
    with pytest.raises(UnsafeTestTargetError, match="cortexa_agent"):
        assert_database_url_is_safe_for_tests(
            "postgresql+asyncpg://cortexa:x@postgres:5432/cortexa_agent"
        )


def test_database_url_rejects_non_test_suffix() -> None:
    with pytest.raises(UnsafeTestTargetError, match="_test"):
        assert_database_url_is_safe_for_tests(
            "postgresql+asyncpg://cortexa:x@postgres:5432/cortexa_staging"
        )


def test_database_url_accepts_cortexa_agent_test() -> None:
    assert (
        assert_database_url_is_safe_for_tests(
            "postgresql+asyncpg://cortexa:x@postgres-test:5432/cortexa_agent_test"
        )
        == "cortexa_agent_test"
    )


def test_redis_url_rejects_development_host() -> None:
    with pytest.raises(UnsafeTestTargetError, match="redis"):
        assert_redis_url_is_safe_for_tests("redis://redis:6379/0")


def test_redis_url_rejects_localhost_db0() -> None:
    with pytest.raises(UnsafeTestTargetError, match="localhost"):
        assert_redis_url_is_safe_for_tests("redis://127.0.0.1:6379/0")


def test_redis_url_accepts_redis_test() -> None:
    assert_redis_url_is_safe_for_tests("redis://redis-test:6379/0")


def test_refuse_flushall() -> None:
    with pytest.raises(UnsafeTestTargetError, match="FLUSHALL"):
        refuse_redis_flushall()


@pytest.mark.asyncio
async def test_live_session_is_test_database(
    settings: Settings,
    db_session: AsyncSession,
) -> None:
    _ = settings
    name = await assert_safe_test_session(db_session)
    assert name == "cortexa_agent_test"
    assert settings.postgres_db == "cortexa_agent_test"
    assert settings.expected_database_identity == "cortexa-agent-test"
    assert "cortexa_agent_test" in (settings.database_url or "")
    assert "cortexa_agent/" not in (settings.database_url or "")
