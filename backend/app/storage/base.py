"""Storage provider protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStorage(Protocol):
    """Provider-neutral binary object storage."""

    async def put_bytes(self, *, key: str, data: bytes) -> str:
        """Store bytes under a storage key. Returns the key."""

    async def get_bytes(self, *, key: str) -> bytes:
        """Read stored bytes by key."""

    async def delete(self, *, key: str) -> None:
        """Delete an object if it exists (idempotent)."""

    def resolve_safe_path(self, *, key: str) -> str:
        """Return a relative storage key representation safe for logs/API."""
