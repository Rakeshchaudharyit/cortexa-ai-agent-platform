"""Domain-specific LLM errors mapped to safe HTTP responses."""

from __future__ import annotations

from fastapi import status

from app.core.exceptions import AppError


class LLMProviderUnavailableError(AppError):
    """Configured LLM provider could not be reached."""

    def __init__(self, message: str = "LLM provider is unavailable") -> None:
        super().__init__(
            code="llm_provider_unavailable",
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class LLMModelUnavailableError(AppError):
    """Provider is reachable but the configured/requested model is missing."""

    def __init__(self, message: str = "Configured LLM model is not available") -> None:
        super().__init__(
            code="llm_model_unavailable",
            message=message,
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
        )


class LLMRequestTimeoutError(AppError):
    """Provider call exceeded the configured timeout."""

    def __init__(self, message: str = "LLM provider request timed out") -> None:
        super().__init__(
            code="llm_request_timeout",
            message=message,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class LLMInvalidResponseError(AppError):
    """Provider returned a malformed or unexpected response."""

    def __init__(self, message: str = "LLM provider returned an invalid response") -> None:
        super().__init__(
            code="llm_invalid_response",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )


class LLMGenerationError(AppError):
    """Generation failed for a controlled provider/application reason."""

    def __init__(self, message: str = "LLM generation failed") -> None:
        super().__init__(
            code="llm_generation_error",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
