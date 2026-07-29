"""PDF text extractor (no OCR)."""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from app.documents.exceptions import DocumentExtractionError, EmptyDocumentError
from app.documents.extractors.base import normalize_extracted_text
from app.documents.schemas import ExtractedSegment, ExtractionResult

logger = logging.getLogger("cortexa.documents.pdf")


class PdfExtractor:
    media_types = frozenset({"application/pdf"})

    def extract(self, data: bytes, *, media_type: str, filename: str) -> ExtractionResult:
        try:
            reader = PdfReader(io.BytesIO(data), strict=False)
        except PdfReadError as exc:
            raise DocumentExtractionError("PDF document could not be read") from exc
        except Exception as exc:  # noqa: BLE001 — normalize parser failures
            logger.warning("pdf_parse_failed category=unreadable")
            raise DocumentExtractionError("PDF document could not be read") from exc

        if getattr(reader, "is_encrypted", False):
            # pypdf decrypt return codes vary across versions; do not rely on them.
            # Try an empty-password unlock, then verify pages are actually readable.
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise DocumentExtractionError("Encrypted PDF documents are not supported") from exc
            try:
                _ = len(reader.pages)
                if reader.pages:
                    _ = reader.pages[0].extract_text()
            except FileNotDecryptedError as exc:
                raise DocumentExtractionError("Encrypted PDF documents are not supported") from exc
            except Exception as exc:  # noqa: BLE001
                raise DocumentExtractionError("Encrypted PDF documents are not supported") from exc

        segments: list[ExtractedSegment] = []
        pages: list[str] = []
        try:
            for page_number, page in enumerate(reader.pages, start=1):
                raw = page.extract_text() or ""
                normalized_page = normalize_extracted_text(raw)
                if not normalized_page:
                    continue
                pages.append(normalized_page)
                segments.append(
                    ExtractedSegment(
                        text=normalized_page,
                        page_number=page_number,
                        section=f"page-{page_number}",
                    )
                )
        except DocumentExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf_extract_failed category=parser")
            raise DocumentExtractionError("PDF text extraction failed") from exc

        text = normalize_extracted_text("\n\n".join(pages))
        if not text:
            raise EmptyDocumentError("PDF contains no extractable text")
        return ExtractionResult(
            text=text,
            character_count=len(text),
            media_type=media_type,
            segments=segments,
            metadata={"filename": filename, "page_count": len(reader.pages)},
        )
