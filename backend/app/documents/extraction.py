"""Document extraction orchestration."""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.documents.exceptions import (
    DocumentExtractionError,
    EmptyDocumentError,
    UnsupportedDocumentTypeError,
)
from app.documents.extractors.base import DocumentExtractor
from app.documents.extractors.docx import DocxExtractor
from app.documents.extractors.markdown import MarkdownExtractor
from app.documents.extractors.pdf import PdfExtractor
from app.documents.extractors.text import TextExtractor
from app.documents.schemas import ExtractionResult

logger = logging.getLogger("cortexa.documents.extraction")


class ExtractionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        extractors: list[DocumentExtractor] = [
            TextExtractor(),
            MarkdownExtractor(),
            PdfExtractor(),
            DocxExtractor(),
        ]
        self._by_media: dict[str, DocumentExtractor] = {}
        for extractor in extractors:
            for media_type in extractor.media_types:
                self._by_media[media_type] = extractor

    def extract(self, *, data: bytes, media_type: str, filename: str) -> ExtractionResult:
        extractor = self._by_media.get(media_type)
        if extractor is None:
            raise UnsupportedDocumentTypeError()
        logger.info(
            "extraction_start media_type=%s file_size=%s",
            media_type,
            len(data),
        )
        try:
            result = extractor.extract(data, media_type=media_type, filename=filename)
        except (DocumentExtractionError, EmptyDocumentError, UnsupportedDocumentTypeError):
            logger.warning("extraction_failure media_type=%s", media_type)
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("extraction_failure media_type=%s category=unexpected", media_type)
            raise DocumentExtractionError("Document text extraction failed") from exc

        if result.character_count > self._settings.document_max_text_characters:
            raise DocumentExtractionError(
                "Extracted text exceeds the maximum allowed character limit"
            )
        if not result.text.strip():
            raise EmptyDocumentError()

        logger.info(
            "extraction_success media_type=%s character_count=%s segment_count=%s",
            media_type,
            result.character_count,
            len(result.segments),
        )
        return result
