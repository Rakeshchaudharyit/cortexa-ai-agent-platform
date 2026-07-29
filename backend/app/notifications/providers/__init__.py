"""Concrete notification delivery providers."""

from app.notifications.providers.development import DevelopmentPasswordResetDelivery

__all__ = ["DevelopmentPasswordResetDelivery"]
