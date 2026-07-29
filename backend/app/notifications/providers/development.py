"""Development-only password-reset delivery via Redis (no real email)."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.core.config import Settings
from app.notifications.base import PasswordResetMessage
from app.schemas.auth import normalize_email

logger = logging.getLogger("cortexa.notifications.password_reset")

_DEV_DELIVERY_KEY_PREFIX = "cortexa:pwd_reset:dev_delivery:"


@dataclass
class DevelopmentPasswordResetDelivery:
    """Stores the latest reset URL in Redis for CLI retrieval. Never sends email.

    Raw reset URLs live only in Redis (never PostgreSQL). Keys use an HMAC of the
    normalized email so plaintext addresses are never part of the key.
    """

    settings: Settings
    redis: Any | None = None

    def delivery_key(self, email: str) -> str:
        """Redis key for an email — digest only, never plaintext."""
        normalized = normalize_email(email)
        digest = hmac.new(
            self.settings.jwt_secret_key.encode("utf-8"),
            normalized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{_DEV_DELIVERY_KEY_PREFIX}{digest}"

    def _ttl_seconds(self) -> int:
        minutes = self.settings.password_reset_token_expire_minutes
        return max(1, int(minutes) * 60)

    def _require_non_production(self) -> None:
        if self.settings.is_production or self.settings.app_env == "production":
            raise RuntimeError("Development password-reset delivery is disabled in production.")

    async def send_password_reset(self, message: PasswordResetMessage) -> None:
        self._require_non_production()
        if self.redis is None:
            raise RuntimeError("Redis is required for development password-reset delivery")
        key = self.delivery_key(message.email)
        ttl = self._ttl_seconds()
        # SET replaces any previous delivery value for this email.
        await self.redis.set(key, message.reset_url, ex=ttl)
        logger.info(
            "password_reset_dev_delivery_stored outcome=ok expires_at=%s ttl_seconds=%s",
            message.expires_at_iso,
            ttl,
        )

    async def consume_latest_reset_url(self, email: str) -> str | None:
        """Return and delete the latest stored reset URL (development/CLI only)."""
        self._require_non_production()
        if self.redis is None:
            return None
        key = self.delivery_key(email)
        getdel = getattr(self.redis, "getdel", None)
        if callable(getdel):
            value = await getdel(key)
        else:
            value = await self.redis.get(key)
            if value is not None:
                await self.redis.delete(key)
        if value is None:
            return None
        return str(value)

    async def get_latest_reset_url(self, email: str) -> str | None:
        """Peek at the latest URL without deleting (tests / diagnostics)."""
        if self.settings.is_production or self.settings.app_env == "production":
            return None
        if self.redis is None:
            return None
        key = self.delivery_key(email)
        value = await self.redis.get(key)
        if value is None:
            return None
        return str(value)

    async def clear(self) -> None:
        """Best-effort clear of delivery keys (tests). No-op without Redis."""
        if self.redis is None:
            return
        pattern = f"{_DEV_DELIVERY_KEY_PREFIX}*"
        scan_iter = getattr(self.redis, "scan_iter", None)
        if callable(scan_iter):
            keys: list[str] = []
            async for key in scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
            return
        # Fake Redis may expose a simple dict.
        store = getattr(self.redis, "_store", None)
        if isinstance(store, dict):
            for key in list(store):
                if str(key).startswith(_DEV_DELIVERY_KEY_PREFIX):
                    store.pop(key, None)


def build_reset_url(*, frontend_url: str, raw_token: str) -> str:
    """Build a reset URL. Token is query-only; never logged by callers."""
    base = frontend_url.strip()
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}token={quote(raw_token, safe='')}"
