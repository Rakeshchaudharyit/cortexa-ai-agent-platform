"""Document upload validation tests."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.documents.exceptions import (
    DocumentTooLargeError,
    DocumentUploadDisabledError,
    EmptyDocumentError,
    UnsupportedDocumentTypeError,
)
from app.documents.validation import sanitize_filename, validate_upload

from tests.document_helpers import make_docx_bytes, make_pdf_bytes, sample_txt_bytes


def test_validate_txt_upload(settings: Settings) -> None:
    data = sample_txt_bytes()
    validated = validate_upload(
        filename="notes.txt",
        content_type="text/plain",
        data=data,
        settings=settings,
    )
    assert validated.extension == ".txt"
    assert validated.media_type == "text/plain"
    assert validated.file_size_bytes == len(data)
    assert len(validated.checksum_sha256) == 64


def test_validate_pdf_and_docx(settings: Settings) -> None:
    pdf = validate_upload(
        filename="doc.pdf",
        content_type="application/pdf",
        data=make_pdf_bytes(),
        settings=settings,
    )
    assert pdf.extension == ".pdf"
    assert pdf.media_type == "application/pdf"

    docx = validate_upload(
        filename="doc.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data=make_docx_bytes(),
        settings=settings,
    )
    assert docx.extension == ".docx"


def test_reject_unsupported_extension(settings: Settings) -> None:
    with pytest.raises(UnsupportedDocumentTypeError):
        validate_upload(
            filename="malware.exe",
            content_type="application/octet-stream",
            data=b"MZ",
            settings=settings,
        )


def test_reject_empty_upload(settings: Settings) -> None:
    with pytest.raises(EmptyDocumentError):
        validate_upload(
            filename="empty.txt",
            content_type="text/plain",
            data=b"",
            settings=settings,
        )


def test_reject_oversized_upload(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_MAX_FILE_SIZE_BYTES", "1024")
    from app.core.config import clear_settings_cache

    clear_settings_cache()
    tight = Settings()
    with pytest.raises(DocumentTooLargeError):
        validate_upload(
            filename="big.txt",
            content_type="text/plain",
            data=b"x" * 2048,
            settings=tight,
        )
    clear_settings_cache()


def test_reject_path_traversal_filename(settings: Settings) -> None:
    with pytest.raises(UnsupportedDocumentTypeError):
        sanitize_filename("../etc/passwd.txt")


def test_reject_mismatched_pdf_contents(settings: Settings) -> None:
    with pytest.raises(UnsupportedDocumentTypeError):
        validate_upload(
            filename="fake.pdf",
            content_type="application/pdf",
            data=b"this is not a pdf",
            settings=settings,
        )


def test_reject_when_upload_disabled(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_UPLOAD_ENABLED", "false")
    from app.core.config import clear_settings_cache

    clear_settings_cache()
    disabled = Settings()
    with pytest.raises(DocumentUploadDisabledError):
        validate_upload(
            filename="notes.txt",
            content_type="text/plain",
            data=b"hello world",
            settings=disabled,
        )
    clear_settings_cache()


def test_sanitize_filename_strips_directories(settings: Settings) -> None:
    _ = settings
    assert sanitize_filename("folder/sub/notes.txt") == "notes.txt"
