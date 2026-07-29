"""Password-reset delivery factory."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.notifications.base import PasswordResetMessage
from app.notifications.providers.development import DevelopmentPasswordResetDelivery

__all__ = [
    "PasswordResetMessage",
    "create_password_reset_delivery",
]


def create_password_reset_delivery(
    settings: Settings,
    *,
    redis: Any | None = None,
) -> DevelopmentPasswordResetDelivery:
    """Return the configured delivery provider (Redis development sink for Phase 5.1)."""
    # Phase 5.1 only ships the development sink; SMTP remains a later task.
    _ = settings.password_reset_delivery_provider
    return DevelopmentPasswordResetDelivery(settings=settings, redis=redis)
