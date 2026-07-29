"""DOCX paragraph and table extractor (no macros / embedded objects)."""

from __future__ import annotations

import io
import logging
import zipfile

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.documents.exceptions import DocumentExtractionError, EmptyDocumentError
from app.documents.extractors.base import normalize_extracted_text
from app.documents.schemas import ExtractedSegment, ExtractionResult

logger = logging.getLogger("cortexa.documents.docx")

# DOCX is a ZIP; reject non-ZIP and obviously unsafe packages early.
_DOCX_MAGIC = b"PK"


class DocxExtractor:
    media_types = frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    )

    def extract(self, data: bytes, *, media_type: str, filename: str) -> ExtractionResult:
        if not data.startswith(_DOCX_MAGIC):
            raise DocumentExtractionError("DOCX document signature is invalid")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if any(name.startswith(("../", "/")) or ".." in name for name in names):
                    raise DocumentExtractionError("DOCX package contains unsafe paths")
                # Ignore macros / VBA / embedded objects; only require document.xml.
                if "word/document.xml" not in names:
                    raise DocumentExtractionError("DOCX document is missing required content")
            document = DocxDocument(io.BytesIO(data))
        except DocumentExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("docx_parse_failed category=unreadable")
            raise DocumentExtractionError("DOCX document could not be read") from exc

        segments: list[ExtractedSegment] = []
        parts: list[str] = []
        paragraph_index = 0
        try:
            for block in document.element.body:
                tag = block.tag.split("}")[-1]
                if tag == "p":
                    paragraph = Paragraph(block, document)
                    text = normalize_extracted_text(paragraph.text)
                    if not text:
                        continue
                    parts.append(text)
                    segments.append(
                        ExtractedSegment(
                            text=text,
                            section="paragraph",
                            paragraph_index=paragraph_index,
                        )
                    )
                    paragraph_index += 1
                elif tag == "tbl":
                    table = Table(block, document)
                    rows: list[str] = []
                    for row in table.rows:
                        cells = [
                            normalize_extracted_text(cell.text)
                            for cell in row.cells
                            if normalize_extracted_text(cell.text)
                        ]
                        if cells:
                            rows.append(" | ".join(cells))
                    if not rows:
                        continue
                    table_text = "\n".join(rows)
                    parts.append(table_text)
                    segments.append(
                        ExtractedSegment(
                            text=table_text,
                            section="table",
                            paragraph_index=paragraph_index,
                        )
                    )
                    paragraph_index += 1
        except DocumentExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("docx_extract_failed category=parser")
            raise DocumentExtractionError("DOCX text extraction failed") from exc

        text = normalize_extracted_text("\n\n".join(parts))
        if not text:
            raise EmptyDocumentError("DOCX contains no extractable text")
        return ExtractionResult(
            text=text,
            character_count=len(text),
            media_type=media_type,
            segments=segments,
            metadata={"filename": filename},
        )
