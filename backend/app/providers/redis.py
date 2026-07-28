"""Async Redis client provider."""

from __future__ import annotations

import logging
from typing import Any, cast

from redis.asyncio import Redis

from app.core.config import Settings

logger = logging.getLogger("cortexa.redis")

_redis_client: Redis[Any] | None = None


async def init_redis(settings: Settings) -> Redis[Any]:
    """Create a Redis client. Idempotent for process lifetime."""
    global _redis_client
    if _redis_client is None:
        redis_url = settings.redis_url
        if not redis_url:
            raise RuntimeError("REDIS_URL is not configured")
        _redis_client = Redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def get_redis() -> Redis[Any]:
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return _redis_client


async def check_redis(client: Redis[Any] | None = None) -> tuple[bool, str | None]:
    """PING Redis. Returns (ok, sanitized_message_on_failure)."""
    try:
        redis = client or get_redis()
        response = await redis.ping()
        if response is True or cast(object, response) in {b"PONG", "PONG"}:
            return True, None
        logger.error("redis_ping_unexpected_response")
        return False, "Redis unavailable"
    except Exception:
        logger.exception("redis_health_check_failed")
        return False, "Redis unavailable"


async def close_redis() -> None:
    """Close the Redis client and clear module state."""
    global _redis_client
    if _redis_client is not None:
        close = getattr(_redis_client, "aclose", None)
        if callable(close):
            await close()
        else:
            await _redis_client.close()
    _redis_client = None


def reset_redis_state() -> None:
    """Synchronous reset for unit tests that never opened connections."""
    global _redis_client
    _redis_client = None
