"""Normalized LLM request/response models shared across providers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class ToolCallRequest(BaseModel):
    """Tool call attached to an assistant message (provider-neutral)."""

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(default="", max_length=100_000)
    tool_calls: list[ToolCallRequest] | None = None
    tool_call_id: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=64)

    @field_validator("content")
    @classmethod
    def content_rules(cls, value: str) -> str:
        return value

    @model_validator(mode="after")
    def validate_message_shape(self) -> ChatMessage:
        if self.role == MessageRole.tool:
            if not self.tool_call_id:
                raise ValueError("tool messages require tool_call_id")
            if not self.content.strip():
                raise ValueError("tool message content cannot be blank")
            return self
        if self.tool_calls:
            return self
        if not self.content.strip():
            raise ValueError("Message content cannot be blank")
        return self


class ProviderToolSpec(BaseModel):
    """Minimal provider tool schema wrapper."""

    type: str = "function"
    function: dict[str, Any]


class GenerateRequest(BaseModel):
    """Client generation request. Optional fields fall back to settings."""

    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Model name override; defaults to the configured provider model.",
    )
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature in [0.0, 2.0].",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=8192,
        description="Maximum completion tokens; capped by LLM_MAX_OUTPUT_TOKENS.",
    )
    system: str | None = Field(
        default=None,
        max_length=32_000,
        description="Optional system prompt prepended as a system message.",
    )
    stop: list[str] | None = Field(
        default=None,
        max_length=16,
        description="Optional stop sequences.",
    )
    tools: list[ProviderToolSpec] | None = Field(
        default=None,
        max_length=32,
        description="Optional provider-compatible tool schemas.",
    )
    tool_choice: str | None = Field(
        default=None,
        max_length=64,
        description="Optional tool choice hint (auto/none/required).",
    )

    @field_validator("system")
    @classmethod
    def system_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("System prompt cannot be blank")
        return value

    @field_validator("stop")
    @classmethod
    def stop_sequences_valid(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("Stop sequences cannot be blank")
            if len(text) > 200:
                raise ValueError("Stop sequence is too long")
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def require_user_or_assistant_content(self) -> GenerateRequest:
        if not self.messages and self.system is None:
            raise ValueError("At least one message is required")
        return self


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class GenerateResponse(BaseModel):
    provider: str
    model: str
    content: str = ""
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    latency_ms: float | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMStatus(str, Enum):
    ready = "ready"
    model_unavailable = "model_unavailable"
    provider_unavailable = "provider_unavailable"
    misconfigured = "misconfigured"


class LLMStatusResponse(BaseModel):
    provider: str
    model: str
    provider_reachable: bool
    model_available: bool
    status: LLMStatus
    message: str


class StreamEventType(str, Enum):
    start = "start"
    delta = "delta"
    citation = "citation"
    metadata = "metadata"
    complete = "complete"
    error = "error"
    # RAG / generation progress (safe status text only — no document contents)
    progress = "progress"
    # Phase 6 agent/tool lifecycle (backward-compatible additions)
    agent_started = "agent_started"
    tool_call_started = "tool_call_started"
    tool_call_arguments = "tool_call_arguments"
    tool_execution_started = "tool_execution_started"
    tool_execution_succeeded = "tool_execution_succeeded"
    tool_execution_failed = "tool_execution_failed"
    assistant_token = "assistant_token"
    assistant_completed = "assistant_completed"
    agent_completed = "agent_completed"
    agent_failed = "agent_failed"
    # Phase 7 long-term memory lifecycle (backward-compatible additions)
    memory_retrieval_started = "memory_retrieval_started"
    memory_retrieval_completed = "memory_retrieval_completed"
    memory_candidate_proposed = "memory_candidate_proposed"
    memory_saved = "memory_saved"
    memory_updated = "memory_updated"
    memory_archived = "memory_archived"
    memory_deleted = "memory_deleted"
    memory_action_failed = "memory_action_failed"


class StreamEvent(BaseModel):
    """Normalized streaming event emitted as SSE."""

    event: StreamEventType
    data: dict[str, Any]

    def to_sse(self) -> str:
        import json

        payload = json.dumps(self.data, separators=(",", ":"), ensure_ascii=False)
        return f"event: {self.event.value}\ndata: {payload}\n\n"


class ProviderHealthResult(BaseModel):
    provider: str
    model: str
    provider_reachable: bool
    model_available: bool
    status: LLMStatus
    message: str
