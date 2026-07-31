"""Tool execution context — approved fields only, never raw HTTP requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole


@dataclass
class ToolExecutionContext:
    """Approved information available to tool implementations."""

    session: AsyncSession
    user_id: uuid.UUID
    user_role: UserRole
    request_id: str | None = None
    correlation_id: str | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    locale: str | None = None
    timezone: str | None = None
    allowed_document_ids: list[uuid.UUID] | None = None
    cancelled: bool = False
    clock: datetime | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    # Services injected by the executor/orchestrator for built-ins.
    retrieval_service: Any | None = None
    llm_service: Any | None = None
    settings: Any | None = None
    # Prevent recursive invocation of the same tool within one agent turn.
    active_tool_stack: list[str] = field(default_factory=list)
