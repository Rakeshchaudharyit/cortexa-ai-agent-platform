"""Readiness endpoint tests with mocked dependency checks."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import StubHealthService


async def _client_for(service: StubHealthService, settings: Settings) -> AsyncClient:
    app = create_app(settings)
    app.state.health_service = service
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_ready_returns_200_when_dependencies_pass(settings: Settings) -> None:
    service = StubHealthService(settings, db_ok=True, redis_ok=True)
    async with await _client_for(service, settings) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "ok"
    assert payload["checks"]["database"].get("message") is None
    assert payload["checks"]["redis"].get("message") is None


@pytest.mark.asyncio
async def test_ready_returns_503_when_database_fails(settings: Settings) -> None:
    service = StubHealthService(settings, db_ok=False, redis_ok=True)
    async with await _client_for(service, settings) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["status"] == "error"
    assert payload["checks"]["database"]["message"] == "Database unavailable"
    assert payload["checks"]["redis"]["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_redis_fails(settings: Settings) -> None:
    service = StubHealthService(settings, db_ok=True, redis_ok=False)
    async with await _client_for(service, settings) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["redis"]["status"] == "error"
    assert payload["checks"]["redis"]["message"] == "Redis unavailable"
    assert payload["checks"]["database"]["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_reports_dependencies_independently(settings: Settings) -> None:
    service = StubHealthService(settings, db_ok=False, redis_ok=False)
    async with await _client_for(service, settings) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["checks"]["database"]["status"] == "error"
    assert payload["checks"]["redis"]["status"] == "error"
    # Sanitized messages only — no hostnames or connection strings.
    body = response.text.lower()
    assert "localhost" not in body
    assert "postgresql" not in body
    assert "redis://" not in body
    assert "traceback" not in body


@pytest.mark.asyncio
async def test_system_info_ollama_feature_enabled(client: AsyncClient, app: FastAPI) -> None:
    response = await client.get("/api/v1/system/info")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Cortexa AI Agent Platform"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "test"
    assert payload["api_version"] == "v1"
    assert payload["features"] == {
        "ollama": True,
        "auth": True,
        "rag": True,
        "memory": True,
        "tools": True,
        "voice": False,
        "password_reset_dev_notice": True,
    }
