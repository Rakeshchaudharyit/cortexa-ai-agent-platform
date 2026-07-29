"""Storage package."""

from app.storage.base import ObjectStorage
from app.storage.local import LocalFilesystemStorage

__all__ = ["LocalFilesystemStorage", "ObjectStorage"]
