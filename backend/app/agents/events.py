"""Agent event helpers (re-exports stream event types for documentation clarity)."""

from __future__ import annotations

from app.llm.schemas import StreamEvent, StreamEventType

AGENT_EVENT_TYPES: tuple[StreamEventType, ...] = (
    StreamEventType.agent_started,
    StreamEventType.tool_call_started,
    StreamEventType.tool_call_arguments,
    StreamEventType.tool_execution_started,
    StreamEventType.tool_execution_succeeded,
    StreamEventType.tool_execution_failed,
    StreamEventType.assistant_token,
    StreamEventType.assistant_completed,
    StreamEventType.agent_completed,
    StreamEventType.agent_failed,
)

__all__ = ["AGENT_EVENT_TYPES", "StreamEvent", "StreamEventType"]
