"""Provider-neutral password-reset delivery interface and message model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PasswordResetMessage:
    """Safe delivery payload — raw token only used to build the reset URL."""

    email: str
    reset_url: str
    expires_at_iso: str


class PasswordResetDelivery(Protocol):
    """Deliver a password-reset link without exposing tokens on public APIs."""

    async def send_password_reset(self, message: PasswordResetMessage) -> None:
        """Deliver reset instructions. Must not raise enumeration-safe path errors."""
