"""Local filesystem object storage with path-traversal protections."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from app.storage.exceptions import StorageConflictError, StorageError, StorageNotFoundError

logger = logging.getLogger("cortexa.storage.local")


def _validate_key(key: str) -> str:
    cleaned = key.strip()
    if not cleaned:
        raise StorageError(
            "Storage key cannot be blank",
            code="invalid_storage_key",
            status_code=400,
        )
    if "\x00" in cleaned:
        raise StorageError(
            "Storage key contains invalid characters",
            code="invalid_storage_key",
            status_code=400,
        )
    if cleaned.startswith(("/", "\\")) or ".." in cleaned.split("/"):
        raise StorageError(
            "Storage key path is unsafe",
            code="invalid_storage_key",
            status_code=400,
        )
    return cleaned


class LocalFilesystemStorage:
    """Atomic local filesystem storage under a configured root directory."""

    def __init__(self, *, root_path: str) -> None:
        self._root = Path(root_path).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        if not self._root.is_dir() or self._root.is_symlink():
            raise StorageError("Document storage root is not a usable directory")

    @property
    def root_path(self) -> Path:
        return self._root

    def _absolute_path(self, key: str) -> Path:
        safe_key = _validate_key(key)
        candidate = (self._root / safe_key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise StorageError(
                "Storage key path is unsafe",
                code="invalid_storage_key",
                status_code=400,
            ) from exc
        if candidate.is_symlink():
            raise StorageError("Symbolic links are not allowed in document storage")
        return candidate

    def resolve_safe_path(self, *, key: str) -> str:
        return _validate_key(key)

    async def put_bytes(self, *, key: str, data: bytes) -> str:
        return await asyncio.to_thread(self._put_bytes_sync, key, data)

    def _put_bytes_sync(self, key: str, data: bytes) -> str:
        path = self._absolute_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise StorageConflictError()
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                delete=False,
                prefix=f".{path.name}.",
                suffix=".tmp",
            ) as handle:
                tmp_path = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            tmp_path = None
        except StorageConflictError:
            raise
        except OSError as exc:
            logger.warning("storage_put_failed category=os_error")
            raise StorageError("Failed to store document file") from exc
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        return _validate_key(key)

    async def get_bytes(self, *, key: str) -> bytes:
        return await asyncio.to_thread(self._get_bytes_sync, key)

    def _get_bytes_sync(self, key: str) -> bytes:
        path = self._absolute_path(key)
        if not path.is_file() or path.is_symlink():
            raise StorageNotFoundError()
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError("Failed to read stored document file") from exc

    async def delete(self, *, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    def _delete_sync(self, key: str) -> None:
        path = self._absolute_path(key)
        try:
            if path.is_file() and not path.is_symlink():
                path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Failed to delete stored document file") from exc
