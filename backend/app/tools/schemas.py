"""Provider-neutral and API-facing tool schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ToolSpec(BaseModel):
    """Provider-compatible tool/function schema entry."""

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=2000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"
    category: str = "general"


class ToolCall(BaseModel):
    """Normalized tool call requested by a provider."""

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallDelta(BaseModel):
    """Incremental tool-call fragment during streaming (when supported)."""

    id: str | None = None
    name: str | None = None
    arguments_delta: str | None = None


class ToolResultPayload(BaseModel):
    """Normalized tool execution outcome returned to the orchestrator/LLM."""

    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    expose_to_llm: bool = True


class ToolResultMessage(BaseModel):
    """Provider-neutral tool-result message."""

    tool_call_id: str
    name: str
    content: str
    success: bool = True


class AgentProviderResponse(BaseModel):
    """Normalized provider turn used by the agent loop."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict[str, Any] | None = None
    latency_ms: float | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class ToolDefinitionResponse(BaseModel):
    """Safe public tool listing entry for the current user."""

    name: str
    description: str
    version: str
    category: str
    requires_confirmation: bool
    enabled: bool
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    tools: list[ToolDefinitionResponse]
    total: int


class ToolExecutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool_name: str
    tool_version: str
    status: str
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    arguments_summary: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    created_at: datetime


class ToolExecutionDetail(ToolExecutionSummary):
    arguments_json: dict[str, Any] | None = None
    result_json: dict[str, Any] | None = None
    correlation_id: str | None = None


class ToolExecutionListResponse(BaseModel):
    items: list[ToolExecutionSummary]
    total: int
    limit: int
    offset: int
