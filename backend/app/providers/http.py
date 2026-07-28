"""Shared async HTTP client for outbound provider calls."""

from __future__ import annotations

import httpx

from app.core.config import Settings

_http_client: httpx.AsyncClient | None = None


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    """Create an application-scoped httpx client with explicit timeouts."""
    timeout = httpx.Timeout(
        connect=settings.ollama_connect_timeout_seconds,
        read=settings.ollama_request_timeout_seconds,
        write=settings.ollama_request_timeout_seconds,
        pool=settings.ollama_connect_timeout_seconds,
    )
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        headers={"User-Agent": "cortexa-backend/0.1"},
    )


async def init_http_client(settings: Settings) -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = build_http_client(settings)
    return _http_client


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client is not initialized")
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def reset_http_client_state() -> None:
    """Synchronous reset for unit tests that never opened connections."""
    global _http_client
    _http_client = None
