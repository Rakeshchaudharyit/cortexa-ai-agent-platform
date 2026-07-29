"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.router import build_api_router, build_root_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.db.session import init_engine
from app.services.health import HealthService


class RequestIdMiddleware:
    """Assign or propagate X-Request-ID for correlation (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                raw_headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_ctx.reset(token)


class RequestLoggingMiddleware:
    """Log method, path, status, and duration. Never log bodies (pure ASGI)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = get_logger("cortexa.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "-")
        path = scope.get("path", "-")
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._logger.info(
                "request_completed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        description=(
            "Cortexa AI Agent Platform API — Phase 4 RAG foundation with authenticated "
            "document ingestion, embeddings, retrieval, and grounded answers. "
            "Memory, tools, and voice are not available yet."
        ),
        lifespan=lifespan,
        docs_url="/docs" if not resolved.is_production else None,
        redoc_url="/redoc" if not resolved.is_production else None,
    )

    # Stash settings early so tests can override services before lifespan.
    app.state.settings = resolved
    app.state.health_service = HealthService(settings=resolved)
    # Ensure session factory exists even when lifespan is not exercised (unit tests).
    init_engine(resolved)
    # LLM service is attached during lifespan (live) or by tests (stub/fake).

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)
    app.include_router(build_root_router())
    app.include_router(build_api_router(resolved))

    return app


app = create_app()
