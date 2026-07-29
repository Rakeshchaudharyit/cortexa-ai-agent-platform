"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine from settings. Idempotent for process lifetime.

    The Docker entrypoint applies Alembic migrations *before* Uvicorn starts, so
    this pool is created against the post-migration schema. Do not keep a long-
    lived backend process across `alembic upgrade` on a shared database — restart
    the backend after applying migrations so asyncpg cannot reuse stale type OIDs
    or prepared statements (e.g. "cache lookup failed for type").
    """
    global _engine, _session_factory
    if _engine is None:
        database_url = settings.database_url
        if not database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        _engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            # Avoid caching prepared statements across DDL / type OID changes.
            connect_args={"statement_cache_size": 0},
            echo=False,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database session factory is not initialized")
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for request-scoped sessions (unused in Phase 1 routes)."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine and clear module state."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_engine_state() -> None:
    """Synchronous reset for unit tests that never opened connections."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
