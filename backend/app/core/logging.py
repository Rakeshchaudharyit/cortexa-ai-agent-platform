"""Structured logging configuration for the backend."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

SENSITIVE_HEADER_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "proxy-authorization",
    }
)


class RequestContextFilter(logging.Filter):
    """Inject request_id into every log record when available."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__["request_id"] = request_id_ctx.get() or "-"
        return True


class StructuredFormatter(logging.Formatter):
    """Human-readable structured log lines without secrets."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "-")
        base = (
            f"ts={self.formatTime(record, self.datefmt)} "
            f"level={record.levelname} "
            f"logger={record.name} "
            f"request_id={request_id} "
            f"msg={record.getMessage()}"
        )
        extras: list[str] = []
        for key in ("method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                extras.append(f"{key}={value}")
        if extras:
            return f"{base} {' '.join(extras)}"
        return base


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once for the application."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        StructuredFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"),
    )
    handler.addFilter(RequestContextFilter())
    root.addHandler(handler)

    # Quiet noisy third-party loggers in local development.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive headers for safe diagnostic use."""
    return {
        key: ("[REDACTED]" if key.lower() in SENSITIVE_HEADER_KEYS else value)
        for key, value in headers.items()
    }
