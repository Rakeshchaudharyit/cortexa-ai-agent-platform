"""Tool-domain exceptions with stable, client-safe error codes."""

from __future__ import annotations

from typing import Any

from fastapi import status

from app.core.exceptions import AppError


class ToolError(AppError):
    """Base tool error. Message is safe for clients and the LLM."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details or [],
        )


class ToolNotFoundError(ToolError):
    def __init__(self, tool_name: str = "unknown") -> None:
        super().__init__(
            code="tool_not_found",
            message=f"Tool '{tool_name}' is not available",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ToolDisabledError(ToolError):
    def __init__(self, tool_name: str = "unknown") -> None:
        super().__init__(
            code="tool_disabled",
            message=f"Tool '{tool_name}' is disabled",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ToolPermissionDeniedError(ToolError):
    def __init__(self, tool_name: str = "unknown") -> None:
        super().__init__(
            code="permission_denied",
            message=f"You are not permitted to use tool '{tool_name}'",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ToolInvalidArgumentsError(ToolError):
    def __init__(self, message: str = "Tool arguments are invalid") -> None:
        super().__init__(
            code="invalid_arguments",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class ToolExecutionFailedError(ToolError):
    def __init__(self, message: str = "Tool execution failed") -> None:
        super().__init__(
            code="execution_failed",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ToolExecutionTimeoutError(ToolError):
    def __init__(self, tool_name: str = "unknown") -> None:
        super().__init__(
            code="execution_timeout",
            message=f"Tool '{tool_name}' timed out",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        )


class ToolResultTooLargeError(ToolError):
    def __init__(self) -> None:
        super().__init__(
            code="result_too_large",
            message="Tool result exceeded the configured size limit",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class ToolConfirmationRequiredError(ToolError):
    def __init__(self, tool_name: str = "unknown") -> None:
        super().__init__(
            code="confirmation_required",
            message=f"Tool '{tool_name}' requires confirmation before execution",
            status_code=status.HTTP_409_CONFLICT,
        )


class ToolRegistryError(ToolError):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="tool_registry_error",
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
