"""Extractor registry."""

from app.documents.extractors.docx import DocxExtractor
from app.documents.extractors.markdown import MarkdownExtractor
from app.documents.extractors.pdf import PdfExtractor
from app.documents.extractors.text import TextExtractor

__all__ = [
    "DocxExtractor",
    "MarkdownExtractor",
    "PdfExtractor",
    "TextExtractor",
]
