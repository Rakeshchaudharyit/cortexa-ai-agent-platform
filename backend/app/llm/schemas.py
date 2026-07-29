"""Normalized LLM request/response models shared across providers."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content cannot be blank")
        return value


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
        # At least one non-system conversational message should exist once system
        # is merged; allow pure system+user/assistant combinations already present.
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
    content: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    latency_ms: float | None = None


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
