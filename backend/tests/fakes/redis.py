"""Minimal async Redis stand-in for password-reset delivery tests."""

from __future__ import annotations

import time
from typing import Any


class FakeRedis:
    """Shared in-memory Redis subset used by development delivery tests."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self.fail_next_set = False
        self.unavailable = False

    def _expired(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return True
        return False

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        if self.unavailable or self.fail_next_set:
            self.fail_next_set = False
            raise ConnectionError("redis unavailable")
        if nx and key in self._store and not self._expired(key):
            return False
        expires_at = time.monotonic() + ex if ex is not None else None
        self._store[key] = (str(value), expires_at)
        return True

    async def get(self, key: str) -> str | None:
        if self.unavailable:
            raise ConnectionError("redis unavailable")
        if self._expired(key):
            return None
        entry = self._store.get(key)
        return None if entry is None else entry[0]

    async def getdel(self, key: str) -> str | None:
        if self.unavailable:
            raise ConnectionError("redis unavailable")
        if self._expired(key):
            return None
        entry = self._store.pop(key, None)
        return None if entry is None else entry[0]

    async def delete(self, *keys: str) -> int:
        if self.unavailable:
            raise ConnectionError("redis unavailable")
        removed = 0
        for key in keys:
            if self._store.pop(key, None) is not None:
                removed += 1
        return removed

    async def ttl(self, key: str) -> int:
        if self.unavailable:
            raise ConnectionError("redis unavailable")
        if self._expired(key):
            return -2
        entry = self._store.get(key)
        if entry is None:
            return -2
        _value, expires_at = entry
        if expires_at is None:
            return -1
        remaining = int(expires_at - time.monotonic())
        return max(0, remaining)

    async def expire(self, key: str, seconds: int) -> bool:
        if self.unavailable:
            raise ConnectionError("redis unavailable")
        if self._expired(key):
            return False
        entry = self._store.get(key)
        if entry is None:
            return False
        value, _ = entry
        self._store[key] = (value, time.monotonic() + seconds)
        return True

    async def ping(self) -> bool:
        if self.unavailable:
            raise ConnectionError("redis unavailable")
        return True

    async def scan_iter(self, *, match: str | None = None) -> Any:
        prefix = ""
        if match and match.endswith("*"):
            prefix = match[:-1]
        for key in list(self._store):
            if self._expired(key):
                continue
            if not prefix or str(key).startswith(prefix):
                yield key
