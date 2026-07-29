"""Document extraction tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.core.config import Settings
from app.documents.exceptions import DocumentExtractionError, EmptyDocumentError
from app.documents.extraction import ExtractionService
from app.documents.extractors.pdf import PdfExtractor
from pypdf.errors import FileNotDecryptedError

from tests.document_helpers import (
    make_docx_bytes,
    make_empty_docx_bytes,
    make_empty_pdf_bytes,
    make_invalid_pdf_bytes,
    make_pdf_bytes,
    sample_md_bytes,
    sample_txt_bytes,
)


def test_extract_txt_and_md(settings: Settings) -> None:
    service = ExtractionService(settings)
    txt = service.extract(
        data=sample_txt_bytes(),
        media_type="text/plain",
        filename="sample.txt",
    )
    assert "Cortexa" in txt.text
    assert txt.character_count > 0

    md = service.extract(
        data=sample_md_bytes(),
        media_type="text/markdown",
        filename="sample.md",
    )
    assert "pgvector" in md.text


def test_extract_pdf_and_docx(settings: Settings) -> None:
    service = ExtractionService(settings)
    pdf = service.extract(
        data=make_pdf_bytes("Hello from PDF extraction."),
        media_type="application/pdf",
        filename="hello.pdf",
    )
    assert "Hello from PDF extraction" in pdf.text
    assert pdf.segments

    docx = service.extract(
        data=make_docx_bytes("Hello from DOCX extraction."),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="hello.docx",
    )
    assert "Hello from DOCX extraction" in docx.text


def test_empty_pdf_raises(settings: Settings) -> None:
    service = ExtractionService(settings)
    with pytest.raises(EmptyDocumentError):
        service.extract(
            data=make_empty_pdf_bytes(),
            media_type="application/pdf",
            filename="blank.pdf",
        )


def test_empty_docx_raises(settings: Settings) -> None:
    service = ExtractionService(settings)
    with pytest.raises(EmptyDocumentError):
        service.extract(
            data=make_empty_docx_bytes(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="blank.docx",
        )


def test_invalid_pdf_raises(settings: Settings) -> None:
    service = ExtractionService(settings)
    with pytest.raises(DocumentExtractionError):
        service.extract(
            data=make_invalid_pdf_bytes(),
            media_type="application/pdf",
            filename="bad.pdf",
        )


def test_encrypted_pdf_decrypt_failure() -> None:
    extractor = PdfExtractor()
    fake_reader = MagicMock()
    fake_reader.is_encrypted = True
    fake_reader.decrypt.side_effect = Exception("needs password")
    with patch("app.documents.extractors.pdf.PdfReader", return_value=fake_reader):
        with pytest.raises(DocumentExtractionError, match="Encrypted"):
            extractor.extract(
                data=b"%PDF-1.4 fake",
                media_type="application/pdf",
                filename="secret.pdf",
            )


def test_encrypted_pdf_file_not_decrypted() -> None:
    extractor = PdfExtractor()
    page = MagicMock()
    page.extract_text.side_effect = FileNotDecryptedError("locked")
    fake_reader = MagicMock()
    fake_reader.is_encrypted = True
    fake_reader.decrypt.return_value = 0
    fake_reader.pages = [page]
    with patch("app.documents.extractors.pdf.PdfReader", return_value=fake_reader):
        with pytest.raises(DocumentExtractionError, match="Encrypted"):
            extractor.extract(
                data=b"%PDF-1.4 fake",
                media_type="application/pdf",
                filename="secret.pdf",
            )
