"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from app.api.deps import get_current_active_user
from app.core.config import Settings, clear_settings_cache
from app.db.session import get_session_factory, init_engine, reset_engine_state
from app.main import create_app
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.providers.http import reset_http_client_state
from app.providers.redis import reset_redis_state
from app.schemas.health import DependencyCheck, ReadinessChecks, ReadinessResponse
from app.services.auth import AuthService
from app.services.health import HealthService
from app.services.llm import LLMService
from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from tests.fakes.llm import FakeLLMProvider


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """Isolated settings for unit tests (no real DB/Redis required)."""
    monkeypatch.setenv("APP_NAME", "Cortexa AI Agent Platform")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("API_PREFIX", "/api/v1")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("BACKEND_PORT", "8000")
    monkeypatch.setenv("POSTGRES_HOST", os.environ.get("POSTGRES_HOST", "localhost"))
    monkeypatch.setenv("POSTGRES_PORT", os.environ.get("POSTGRES_PORT", "5432"))
    monkeypatch.setenv("POSTGRES_DB", "cortexa_agent")
    monkeypatch.setenv("POSTGRES_USER", "cortexa")
    monkeypatch.setenv("POSTGRES_PASSWORD", "local_development_only")
    # Prefer Compose DATABASE_URL (postgres host) when running inside Docker.
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://cortexa:local_development_only@localhost:5432/cortexa_agent",
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("REDIS_HOST", os.environ.get("REDIS_HOST", "localhost"))
    monkeypatch.setenv("REDIS_PORT", os.environ.get("REDIS_PORT", "6379"))
    monkeypatch.setenv("REDIS_DB", "0")
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:13000",
    )
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:13000")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-cortexa-jwt-secret-key-32chars-min",
    )
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "14")
    monkeypatch.setenv("AUTH_COOKIE_NAME", "cortexa_refresh")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("AUTH_COOKIE_PATH", "/api/v1/auth")
    monkeypatch.setenv("PASSWORD_MIN_LENGTH", "12")
    monkeypatch.setenv("PASSWORD_MAX_LENGTH", "128")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("OLLAMA_CONNECT_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("LLM_MAX_INPUT_CHARACTERS", "1000")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "256")
    monkeypatch.setenv("LLM_DEFAULT_TEMPERATURE", "0.2")
    clear_settings_cache()
    reset_engine_state()
    reset_redis_state()
    reset_http_client_state()
    resolved = Settings()
    yield resolved
    clear_settings_cache()
    reset_engine_state()
    reset_redis_state()
    reset_http_client_state()


class StubHealthService(HealthService):
    """Health service with injectable readiness outcomes for unit tests."""

    def __init__(
        self,
        settings: Settings,
        *,
        db_ok: bool = True,
        redis_ok: bool = True,
    ) -> None:
        super().__init__(settings=settings, engine=None, redis=None)
        self.db_ok = db_ok
        self.redis_ok = redis_ok

    async def readiness(self) -> tuple[ReadinessResponse, int]:
        checks = ReadinessChecks(
            database=DependencyCheck(
                status="ok" if self.db_ok else "error",
                message=None if self.db_ok else "Database unavailable",
            ),
            redis=DependencyCheck(
                status="ok" if self.redis_ok else "error",
                message=None if self.redis_ok else "Redis unavailable",
            ),
        )
        if self.db_ok and self.redis_ok:
            return ReadinessResponse(status="ready", checks=checks), 200
        return ReadinessResponse(status="not_ready", checks=checks), 503


def make_test_user(
    *,
    status: UserStatus = UserStatus.active,
    role: UserRole = UserRole.user,
    email: str = "user@example.com",
) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="not-a-real-hash",
        full_name="Test User",
        role=role,
        status=status,
        is_email_verified=False,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def fake_llm_provider() -> FakeLLMProvider:
    return FakeLLMProvider(model="qwen2.5:7b")


@pytest.fixture
def app(settings: Settings, fake_llm_provider: FakeLLMProvider) -> FastAPI:
    """Application with stubbed health/LLM services (no live dependencies)."""
    application = create_app(settings)
    application.state.health_service = StubHealthService(settings)
    application.state.llm_service = LLMService(settings=settings, provider=fake_llm_provider)
    application.state.auth_service = AuthService.from_settings(settings)

    # LLM generate/stream require an active user; override so non-auth LLM tests
    # remain independent of the database.
    async def _override_active_user() -> User:
        return make_test_user()

    application.dependency_overrides[get_current_active_user] = _override_active_user

    @application.get("/__test__/validate")
    async def _validate(value: int = Query(...)) -> dict[str, Any]:
        return {"value": value}

    @application.get("/__test__/boom")
    async def _boom() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="secret internal failure detail")

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.fixture
async def db_engine(settings: Settings) -> AsyncIterator[None]:
    """Initialize DB engine against Compose Postgres for auth integration tests."""
    init_engine(settings)
    engine = init_engine(settings)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL unavailable for auth tests: {exc}")
    yield
    reset_engine_state()


@pytest.fixture
async def db_session(db_engine: None) -> AsyncIterator[Any]:
    factory = get_session_factory()
    async with factory() as session:
        # Isolate auth tests without dropping schema.
        await session.execute(text("DELETE FROM refresh_sessions"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()
        yield session
        await session.execute(text("DELETE FROM refresh_sessions"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()


@pytest.fixture
def auth_app(settings: Settings, fake_llm_provider: FakeLLMProvider) -> FastAPI:
    """App for auth API tests — real auth deps, no active-user override."""
    application = create_app(settings)
    application.state.health_service = StubHealthService(settings)
    application.state.llm_service = LLMService(settings=settings, provider=fake_llm_provider)
    application.state.auth_service = AuthService.from_settings(settings)
    init_engine(settings)
    return application


@pytest.fixture
async def auth_client(auth_app: FastAPI, db_session: Any) -> AsyncIterator[AsyncClient]:
    _ = db_session  # ensure tables are cleaned before requests
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={},
    ) as async_client:
        yield async_client
