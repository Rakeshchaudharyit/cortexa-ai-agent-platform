"""Liveness endpoint tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import Settings
from app.main import create_app
from app.services.health import HealthService
from httpx import ASGITransport, AsyncClient

from tests.conftest import StubHealthService


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "backend"
    assert payload["version"] == "0.1.0"
    assert payload["environment"] == "test"
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_health_does_not_require_postgres(settings: Settings) -> None:
    app = create_app(settings)
    app.state.health_service = StubHealthService(settings, db_ok=False, redis_ok=False)

    with (
        patch("app.db.health.check_database", new_callable=AsyncMock) as mock_db,
        patch("app.providers.redis.check_redis", new_callable=AsyncMock) as mock_redis,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_db.assert_not_called()
    mock_redis.assert_not_called()


@pytest.mark.asyncio
async def test_health_does_not_require_redis(settings: Settings) -> None:
    service = HealthService(settings=settings, engine=None, redis=None)
    app = create_app(settings)
    app.state.health_service = service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
