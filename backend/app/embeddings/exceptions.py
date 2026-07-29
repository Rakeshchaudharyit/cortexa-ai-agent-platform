"""Embedding provider exceptions."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class EmbeddingProviderUnavailableError(AppError):
    def __init__(self, message: str = "Embedding provider is unavailable") -> None:
        super().__init__(
            code="embedding_provider_unavailable",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class EmbeddingModelUnavailableError(AppError):
    def __init__(self, message: str = "Configured embedding model is not available") -> None:
        super().__init__(
            code="embedding_model_unavailable",
            message=message,
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
        )


class EmbeddingDimensionMismatchError(AppError):
    def __init__(self, message: str = "Embedding dimension does not match configuration") -> None:
        super().__init__(
            code="embedding_dimension_mismatch",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class EmbeddingTimeoutError(AppError):
    def __init__(self, message: str = "Embedding provider request timed out") -> None:
        super().__init__(
            code="embedding_timeout",
            message=message,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class EmbeddingInvalidResponseError(AppError):
    def __init__(self, message: str = "Embedding provider returned an invalid response") -> None:
        super().__init__(
            code="embedding_invalid_response",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
