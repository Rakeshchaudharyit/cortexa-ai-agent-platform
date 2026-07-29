"""Document domain exceptions mapped to safe HTTP responses."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class UnsupportedDocumentTypeError(AppError):
    def __init__(self, message: str = "Unsupported document type") -> None:
        super().__init__(
            code="unsupported_document_type",
            message=message,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )


class DocumentTooLargeError(AppError):
    def __init__(self, message: str = "Document exceeds the maximum allowed size") -> None:
        super().__init__(
            code="document_too_large",
            message=message,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class EmptyDocumentError(AppError):
    def __init__(self, message: str = "Document contains no extractable text") -> None:
        super().__init__(
            code="empty_document",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class DocumentExtractionError(AppError):
    def __init__(self, message: str = "Document text extraction failed") -> None:
        super().__init__(
            code="document_extraction_failed",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class DocumentNotFoundError(AppError):
    def __init__(self, message: str = "Document not found") -> None:
        super().__init__(
            code="document_not_found",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class DuplicateDocumentError(AppError):
    def __init__(self, message: str = "A document with the same content already exists") -> None:
        super().__init__(
            code="duplicate_document",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class DocumentProcessingError(AppError):
    def __init__(self, message: str = "Document processing failed") -> None:
        super().__init__(
            code="document_processing_failed",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class DocumentUploadDisabledError(AppError):
    def __init__(self, message: str = "Document upload is currently disabled") -> None:
        super().__init__(
            code="document_upload_disabled",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class RetrievalError(AppError):
    def __init__(self, message: str = "Document retrieval failed") -> None:
        super().__init__(
            code="retrieval_error",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class NoRelevantContextError(AppError):
    """Raised internally when no chunks meet the similarity threshold."""

    def __init__(self, message: str = "No relevant document context was found") -> None:
        super().__init__(
            code="no_relevant_context",
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
        )
