"""Application exceptions and FastAPI exception handlers."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx

logger = logging.getLogger("cortexa.errors")


class AppError(Exception):
    """Base application error with a safe client-facing message."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def _resolve_request_id(request: Request) -> str:
    existing = request.headers.get("X-Request-ID") or request_id_ctx.get()
    if existing:
        return existing
    return str(uuid.uuid4())


def error_body(
    *,
    code: str,
    message: str,
    request_id: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        },
        "request_id": request_id,
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach consistent JSON error handlers."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = _resolve_request_id(request)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                details=exc.details,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        request_id = _resolve_request_id(request)
        code = "http_error"
        message = "Request failed"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "not_found"
            message = "Resource not found"
        elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            code = "method_not_allowed"
            message = "Method not allowed"
        elif exc.status_code >= 500:
            code = "internal_error"
            message = "An unexpected error occurred"
        elif isinstance(exc.detail, str):
            message = exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code=code, message=message, request_id=request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = _resolve_request_id(request)
        safe_details: list[dict[str, Any]] = []
        for err in exc.errors():
            # Omit raw input values to avoid leaking request payloads.
            safe_details.append(
                {
                    "loc": list(err.get("loc", [])),
                    "msg": str(err.get("msg", "Invalid value")),
                    "type": str(err.get("type", "value_error")),
                }
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(
                code="validation_error",
                message="Request validation failed",
                request_id=request_id,
                details=safe_details,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = _resolve_request_id(request)
        logger.exception(
            "unhandled_exception path=%s method=%s",
            request.url.path,
            request.method,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body(
                code="internal_error",
                message="An unexpected error occurred",
                request_id=request_id,
            ),
        )
