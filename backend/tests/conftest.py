"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from app.core.config import Settings, clear_settings_cache
from app.db.session import reset_engine_state
from app.main import create_app
from app.providers.http import reset_http_client_state
from app.providers.redis import reset_redis_state
from app.schemas.health import DependencyCheck, ReadinessChecks, ReadinessResponse
from app.services.health import HealthService
from app.services.llm import LLMService
from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient

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
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "cortexa_agent")
    monkeypatch.setenv("POSTGRES_USER", "cortexa")
    monkeypatch.setenv("POSTGRES_PASSWORD", "local_development_only")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://cortexa:local_development_only@localhost:5432/cortexa_agent",
    )
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
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


@pytest.fixture
def fake_llm_provider() -> FakeLLMProvider:
    return FakeLLMProvider(model="qwen2.5:7b")


@pytest.fixture
def app(settings: Settings, fake_llm_provider: FakeLLMProvider) -> FastAPI:
    """Application with stubbed health/LLM services (no live dependencies)."""
    application = create_app(settings)
    application.state.health_service = StubHealthService(settings)
    application.state.llm_service = LLMService(settings=settings, provider=fake_llm_provider)

    # Test-only routes for validation / internal error coverage.
    @application.get("/__test__/validate")
    async def _validate(value: int = Query(...)) -> dict[str, Any]:
        return {"value": value}

    @application.get("/__test__/boom")
    async def _boom() -> None:
        # Use HTTPException so handlers return a safe JSON body under ASGITransport.
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="secret internal failure detail")

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
