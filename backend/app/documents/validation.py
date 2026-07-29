"""Upload validation helpers for documents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.config import Settings
from app.documents.exceptions import (
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentTypeError,
)

_EXTENSION_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".txt": frozenset({"text/plain", "application/octet-stream"}),
    ".md": frozenset(
        {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"}
    ),
    ".pdf": frozenset({"application/pdf", "application/octet-stream"}),
    ".docx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/octet-stream",
            "application/zip",
        }
    ),
}

_CANONICAL_MEDIA_TYPE: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_UNSAFE_FILENAME = re.compile(r"[\x00-\x1f\x7f<>:\"/\\|?*]")


@dataclass(frozen=True)
class ValidatedUpload:
    original_filename: str
    sanitized_filename: str
    extension: str
    media_type: str
    data: bytes
    checksum_sha256: str
    file_size_bytes: int


def sanitize_filename(filename: str) -> str:
    raw = filename.strip().replace("\\", "/")
    if not raw or "\x00" in raw:
        raise UnsupportedDocumentTypeError("Filename is missing or unsafe")
    name = PurePosixPath(raw).name
    if not name or name in {".", ".."}:
        raise UnsupportedDocumentTypeError("Filename is unsafe")
    if name.startswith("/") or ".." in PurePosixPath(raw).parts:
        raise UnsupportedDocumentTypeError("Filename path traversal is not allowed")
    cleaned = _UNSAFE_FILENAME.sub("_", name).strip(" .")
    if not cleaned:
        raise UnsupportedDocumentTypeError("Filename is unsafe")
    return cleaned[:200]


def _detect_extension(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix


def _sniff_media_type(data: bytes, extension: str) -> str | None:
    if extension == ".pdf":
        if data.startswith(b"%PDF"):
            return "application/pdf"
        return None
    if extension == ".docx":
        if data.startswith(b"PK"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return None
    if extension in {".txt", ".md"}:
        # Reject obvious binary for text formats.
        if b"\x00" in data[:4096]:
            return None
        return _CANONICAL_MEDIA_TYPE[extension]
    return None


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    data: bytes,
    settings: Settings,
) -> ValidatedUpload:
    if not settings.document_upload_enabled:
        from app.documents.exceptions import DocumentUploadDisabledError

        raise DocumentUploadDisabledError()

    if not data:
        raise EmptyDocumentError("Uploaded file is empty")

    if len(data) > settings.document_max_file_size_bytes:
        raise DocumentTooLargeError()

    if not filename:
        raise UnsupportedDocumentTypeError("Filename is required")

    sanitized = sanitize_filename(filename)
    extension = _detect_extension(sanitized)
    allowed = {ext.lower() for ext in settings.document_allowed_extensions}
    if extension not in allowed or extension not in _EXTENSION_MEDIA_TYPES:
        raise UnsupportedDocumentTypeError(
            f"File extension '{extension or '(none)'}' is not supported"
        )

    declared = (content_type or "").split(";", 1)[0].strip().lower()
    allowed_media = _EXTENSION_MEDIA_TYPES[extension]
    if declared and declared not in allowed_media and declared != "*/*":
        raise UnsupportedDocumentTypeError(
            "Declared content type does not match the file extension"
        )

    sniffed = _sniff_media_type(data, extension)
    if sniffed is None:
        raise UnsupportedDocumentTypeError("File contents do not match the declared document type")

    canonical = _CANONICAL_MEDIA_TYPE[extension]
    checksum = hashlib.sha256(data).hexdigest()
    return ValidatedUpload(
        original_filename=sanitized,
        sanitized_filename=sanitized,
        extension=extension,
        media_type=canonical,
        data=data,
        checksum_sha256=checksum,
        file_size_bytes=len(data),
    )
