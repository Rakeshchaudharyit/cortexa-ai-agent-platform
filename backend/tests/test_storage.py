"""Local filesystem storage tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.storage.exceptions import StorageConflictError, StorageError, StorageNotFoundError
from app.storage.local import LocalFilesystemStorage


@pytest.mark.asyncio
async def test_atomic_store_and_roundtrip(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root_path=str(tmp_path / "docs"))
    key = await storage.put_bytes(key="user-1/doc-1.txt", data=b"hello cortexa")
    assert key == "user-1/doc-1.txt"
    stored = tmp_path / "docs" / "user-1" / "doc-1.txt"
    assert stored.is_file()
    assert stored.read_bytes() == b"hello cortexa"
    assert await storage.get_bytes(key=key) == b"hello cortexa"


@pytest.mark.asyncio
async def test_reject_path_traversal(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root_path=str(tmp_path / "docs"))
    for key in ("../outside.txt", "user/../../etc/passwd", "/absolute.txt", "a/../b/../../x"):
        with pytest.raises(StorageError):
            await storage.put_bytes(key=key, data=b"nope")


@pytest.mark.asyncio
async def test_reject_blank_and_null_key(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root_path=str(tmp_path / "docs"))
    with pytest.raises(StorageError):
        await storage.put_bytes(key="  ", data=b"x")
    with pytest.raises(StorageError):
        await storage.put_bytes(key="bad\x00key.txt", data=b"x")


@pytest.mark.asyncio
async def test_conflict_and_missing(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root_path=str(tmp_path / "docs"))
    await storage.put_bytes(key="user/a.txt", data=b"one")
    with pytest.raises(StorageConflictError):
        await storage.put_bytes(key="user/a.txt", data=b"two")
    with pytest.raises(StorageNotFoundError):
        await storage.get_bytes(key="user/missing.txt")


@pytest.mark.asyncio
async def test_delete_is_idempotent(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root_path=str(tmp_path / "docs"))
    await storage.put_bytes(key="user/b.txt", data=b"bye")
    await storage.delete(key="user/b.txt")
    await storage.delete(key="user/b.txt")
    with pytest.raises(StorageNotFoundError):
        await storage.get_bytes(key="user/b.txt")
