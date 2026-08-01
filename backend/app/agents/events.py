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

# Internal multi-agent timeline events (persisted on AgentRunEvent; SSE in Phase 9.3).
MULTI_AGENT_EVENT_TYPES: tuple[str, ...] = (
    "run_started",
    "complexity_classified",
    "planning_started",
    "plan_created",
    "safety_checked",
    "task_ready",
    "task_started",
    "task_completed",
    "task_failed",
    "task_skipped",
    "handoff",
    "approval_required",
    "run_completed",
    "run_failed",
    "run_timed_out",
)

__all__ = [
    "AGENT_EVENT_TYPES",
    "MULTI_AGENT_EVENT_TYPES",
    "StreamEvent",
    "StreamEventType",
]
