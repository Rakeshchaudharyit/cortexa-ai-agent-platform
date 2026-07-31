"""Agent orchestration schemas and helpers."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.llm.schemas import ProviderToolSpec, ToolCallRequest
from app.tools.schemas import ToolCall, ToolSpec


def tool_specs_to_provider(tools: list[ToolSpec]) -> list[ProviderToolSpec]:
    return [
        ProviderToolSpec(
            type="function",
            function={
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        )
        for tool in tools
    ]


def tool_calls_from_provider(calls: list[ToolCallRequest]) -> list[ToolCall]:
    return [
        ToolCall(id=call.id, name=call.name, arguments=dict(call.arguments or {})) for call in calls
    ]


def tool_result_content(payload: dict[str, Any] | None, *, success: bool, error: str | None) -> str:
    body: dict[str, Any]
    if success:
        body = {"success": True, "result": payload or {}}
    else:
        body = {"success": False, "error": error or "Tool execution failed"}
    return json.dumps(body, default=str, ensure_ascii=False)


class AgentRunConfig(BaseModel):
    max_iterations: int = Field(default=3, ge=1, le=10)
    temperature: float | None = None
    max_tokens: int | None = None


class AgentRunResult(BaseModel):
    content: str
    tool_execution_ids: list[str] = Field(default_factory=list)
    iterations: int = 0
    finish_reason: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    grounded_from_tools: bool = False
