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
    # Deterministic allow-list from ToolSelectionPolicy (never client-supplied).
    selected_tool_names: list[str] = Field(default_factory=list)
    selection_reason_codes: list[str] = Field(default_factory=list)
    conversation_mode: str = "general"
    memory_context_count: int = 0
    rag_context_count: int = 0


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


# --- Phase 9 multi-agent plan / task contracts (provider-neutral) ---


class AgentPlanTask(BaseModel):
    """One step in a structured multi-agent plan."""

    sequence: int = Field(ge=1, le=64)
    agent_name: str = Field(min_length=1, max_length=64)
    task_type: str = Field(min_length=1, max_length=64)
    objective: str = Field(min_length=1, max_length=1000)
    dependencies: list[int] = Field(default_factory=list, max_length=16)
    allowed_tools: list[str] = Field(default_factory=list, max_length=16)
    expected_output: str = Field(default="", max_length=500)
    requires_approval: bool = False
    maximum_retries: int = Field(default=1, ge=0, le=3)


class AgentPlan(BaseModel):
    """Structured plan produced by the Planning Agent and validated server-side.

    ``reasoning_summary`` must be short, user-safe, and suitable for audit/UI.
    It must never contain hidden chain-of-thought.
    """

    goal: str = Field(min_length=1, max_length=1000)
    requires_multi_agent: bool = True
    reasoning_summary: str = Field(min_length=1, max_length=500)
    tasks: list[AgentPlanTask] = Field(min_length=1, max_length=16)
    final_response_agent: str = Field(default="conversation", min_length=1, max_length=64)
    estimated_steps: int = Field(default=1, ge=1, le=64)
    requires_approval: bool = False


class AgentTaskRequest(BaseModel):
    """Runtime task assignment passed to a specialist agent."""

    task_id: str | None = None
    sequence: int = Field(ge=1, le=64)
    agent_name: str = Field(min_length=1, max_length=64)
    task_type: str = Field(min_length=1, max_length=64)
    objective: str = Field(min_length=1, max_length=1000)
    allowed_tools: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    safe_input_summary: str = Field(default="", max_length=500)


class AgentTaskResult(BaseModel):
    """Safe specialist agent output (no hidden reasoning)."""

    success: bool
    agent_name: str
    task_type: str
    result_summary: str = Field(default="", max_length=2000)
    output: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    approval_action_type: str | None = None
    approval_summary: str | None = Field(default=None, max_length=500)
    error_code: str | None = None
    safe_error_message: str | None = Field(default=None, max_length=500)
    tool_calls_used: int = 0
    llm_calls_used: int = 0


class ComplexityClassification(BaseModel):
    """Deterministic first-pass complexity decision (Phase 9.1 compat)."""

    requires_multi_agent: bool
    reason_codes: list[str] = Field(default_factory=list)
    safe_summary: str = Field(default="", max_length=300)


class AgentComplexityDecision(BaseModel):
    """Authoritative complexity classification for Phase 9.2 coordination."""

    execution_mode: str = Field(pattern="^(single_agent|multi_agent)$")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    required_capabilities: list[str] = Field(default_factory=list, max_length=16)
    suggested_agents: list[str] = Field(default_factory=list, max_length=16)
    requires_planning: bool = False
    requires_approval: bool = False
    safe_summary: str = Field(default="", max_length=300)

    @property
    def requires_multi_agent(self) -> bool:
        return self.execution_mode == "multi_agent"


class AgentExecutionInput(BaseModel):
    """Bounded execution request passed to a specialist agent."""

    run_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None
    objective: str = Field(min_length=1, max_length=1000)
    task_type: str = Field(default="execute", max_length=64)
    agent_name: str = Field(min_length=1, max_length=64)
    allowed_tools: list[str] = Field(default_factory=list, max_length=16)
    limits: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default="", max_length=128)
    requires_approval: bool = False
    safe_input_summary: str = Field(default="", max_length=500)


class AgentExecutionResult(BaseModel):
    """Safe specialist output — no raw provider payloads or hidden reasoning."""

    status: str = Field(default="succeeded", max_length=32)
    safe_summary: str = Field(default="", max_length=2000)
    structured_result: dict[str, Any] = Field(default_factory=dict)
    context_contribution: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    tool_execution_ids: list[str] = Field(default_factory=list, max_length=32)
    memory_action: dict[str, Any] | None = None
    llm_calls_used: int = Field(default=0, ge=0, le=64)
    tool_calls_used: int = Field(default=0, ge=0, le=64)
    retryable: bool = False
    error_code: str | None = None
    safe_error_message: str | None = Field(default=None, max_length=500)
    requires_approval: bool = False
    approval_action_type: str | None = None
    approval_summary: str | None = Field(default=None, max_length=500)

    @property
    def success(self) -> bool:
        return self.status in {"succeeded", "skipped", "approval_required"}


class SafetyDecision(BaseModel):
    """Safety Agent decision over a plan or sensitive action."""

    allowed: bool = True
    requires_approval: bool = False
    blocked: bool = False
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    safe_message: str = Field(default="", max_length=500)
    task_adjustments: list[dict[str, Any]] = Field(default_factory=list, max_length=16)


class ClassifierInput(BaseModel):
    """Inputs for the complexity classifier (no secrets)."""

    user_message: str = Field(max_length=8_000)
    conversation_mode: str = Field(default="general", max_length=32)
    selected_document_ids: list[str] = Field(default_factory=list, max_length=64)
    memory_enabled: bool = False
    explicit_memory_intent: bool = False
    selected_tool_intent: list[str] = Field(default_factory=list, max_length=16)
    conversation_context_summary: str | None = Field(default=None, max_length=2_000)
    enabled_feature_flags: dict[str, bool] = Field(default_factory=dict)


class AgentDefinitionView(BaseModel):
    """Safe public/admin view of a registered agent."""

    key: str
    display_name: str
    description: str
    version: str
    enabled: bool
    system_managed: bool
    capabilities: list[str]
    allowed_tools: list[str]
    maximum_steps: int
    timeout_seconds: int
    required_for_multi_agent: bool = False


class AgentRunSummary(BaseModel):
    id: str
    status: str
    execution_mode: str
    original_request_summary: str
    safe_plan_summary: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    steps_used: int = 0
    llm_calls_used: int = 0
    tool_calls_used: int = 0
    task_count: int = 0
    correlation_id: str
    error_code: str | None = None
    safe_error_message: str | None = None
    created_at: str


class AgentTaskSummary(BaseModel):
    id: str
    assigned_agent_key: str
    task_type: str
    objective: str
    status: str
    sequence: int
    depth: int
    requires_approval: bool
    result_summary: str | None = None
    error_code: str | None = None
    safe_error_message: str | None = None
    retry_count: int = 0
    duration_ms: int | None = None


class AgentApprovalSummary(BaseModel):
    id: str
    agent_run_id: str
    task_id: str
    action_type: str
    status: str
    safe_action_summary: str
    requested_at: str
    expires_at: str | None = None
    resolved_at: str | None = None
    resolution_note: str | None = None


class AgentRunEventSummary(BaseModel):
    id: str
    event_type: str
    agent_key: str | None = None
    task_id: str | None = None
    safe_metadata: dict[str, Any] | None = None
    created_at: str


class AgentDefinitionListResponse(BaseModel):
    items: list[AgentDefinitionView]
    total: int


class AgentRunListResponse(BaseModel):
    items: list[AgentRunSummary]
    total: int
    limit: int
    offset: int


class AgentRunDetailResponse(AgentRunSummary):
    conversation_id: str | None = None
    tasks: list[AgentTaskSummary] = Field(default_factory=list)
    approvals: list[AgentApprovalSummary] = Field(default_factory=list)
    events: list[AgentRunEventSummary] = Field(default_factory=list)


class AgentTaskListResponse(BaseModel):
    items: list[AgentTaskSummary]
    total: int
    limit: int
    offset: int


class AgentEventListResponse(BaseModel):
    items: list[AgentRunEventSummary]
    total: int
    limit: int
    offset: int


class AgentApprovalListResponse(BaseModel):
    items: list[AgentApprovalSummary]
    total: int
    limit: int
    offset: int


class AgentApprovalResolutionRequest(BaseModel):
    resolution_note: str | None = Field(default=None, max_length=500)


class AdminAgentUpdateRequest(BaseModel):
    enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    maximum_steps: int | None = Field(default=None, ge=1, le=32)
    allowed_tools: list[str] | None = Field(default=None, max_length=32)


class AdminAgentRunSummary(AgentRunSummary):
    user_id: str
    conversation_id: str | None = None


class AdminAgentRunListResponse(BaseModel):
    items: list[AdminAgentRunSummary]
    total: int
    limit: int
    offset: int


class AdminAgentRunDetailResponse(AdminAgentRunSummary):
    tasks: list[AgentTaskSummary] = Field(default_factory=list)
    approvals: list[AgentApprovalSummary] = Field(default_factory=list)
    events: list[AgentRunEventSummary] = Field(default_factory=list)
