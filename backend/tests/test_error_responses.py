"""Structured error response and CORS tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_404_safe_response(client: AsyncClient) -> None:
    response = await client.get("/definitely-not-a-route")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["message"] == "Resource not found"
    assert "request_id" in payload
    assert "traceback" not in response.text.lower()
    assert response.headers.get("X-Request-ID") == payload["request_id"]


@pytest.mark.asyncio
async def test_validation_error_safe_response(client: AsyncClient) -> None:
    response = await client.get("/__test__/validate", params={"value": "not-an-int"})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed"
    assert isinstance(payload["error"]["details"], list)
    assert len(payload["error"]["details"]) >= 1
    # Raw input must not be echoed.
    assert "not-an-int" not in response.text
    assert "input" not in str(payload["error"]["details"]).lower() or all(
        "input" not in detail for detail in payload["error"]["details"]
    )
    assert "request_id" in payload


@pytest.mark.asyncio
async def test_internal_error_does_not_leak_details(client: AsyncClient) -> None:
    response = await client.get("/__test__/boom")
    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "internal_error"
    assert payload["error"]["message"] == "An unexpected error occurred"
    assert "secret internal failure" not in response.text
    assert "RuntimeError" not in response.text
    assert "traceback" not in response.text.lower()
    assert "request_id" in payload


@pytest.mark.asyncio
async def test_request_id_propagated_from_header(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "test-corr-id-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-corr-id-123"


@pytest.mark.asyncio
async def test_cors_configuration_applied(client: AsyncClient) -> None:
    response = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    get_response = await client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert get_response.status_code == 200
    assert get_response.headers.get("access-control-allow-origin") == "http://localhost:3000"
