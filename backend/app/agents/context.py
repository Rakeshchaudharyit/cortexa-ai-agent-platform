"""Bounded context envelopes passed between agents."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."


class AgentContextLimits(BaseModel):
    max_characters: int = Field(default=24_000, ge=500, le=100_000)
    max_history_messages: int = Field(default=12, ge=0, le=50)
    max_memory_items: int = Field(default=5, ge=0, le=20)
    max_document_passages: int = Field(default=8, ge=0, le=30)
    max_prior_task_results: int = Field(default=8, ge=0, le=20)
    task_output_max_characters: int = Field(default=8_000, ge=200, le=50_000)


class AgentContextEnvelope(BaseModel):
    """Filtered, budgeted context for a specialist agent.

    Never includes tokens, secrets, full memory stores, raw ORM objects,
    or hidden chain-of-thought.
    """

    user_request: str = Field(max_length=8_000)
    conversation_summary: str | None = Field(default=None, max_length=4_000)
    selected_history: list[dict[str, str]] = Field(default_factory=list)
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    document_context: list[dict[str, Any]] = Field(default_factory=list)
    prior_task_results: list[dict[str, Any]] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    limits: AgentContextLimits = Field(default_factory=AgentContextLimits)
    correlation_id: str = Field(max_length=128)
    conversation_id: UUID | None = None
    user_id: UUID | None = None
    allowed_document_ids: list[UUID] = Field(default_factory=list)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_request", "conversation_summary", mode="before")
    @classmethod
    def _coerce_str(cls, value: object) -> object:
        if value is None:
            return value
        return str(value)

    def enforce_budgets(self) -> AgentContextEnvelope:
        """Return a copy truncated to configured character and item budgets."""
        limits = self.limits
        history = self.selected_history[-limits.max_history_messages :]
        memories = self.memory_context[: limits.max_memory_items]
        docs = self.document_context[: limits.max_document_passages]
        priors = self.prior_task_results[-limits.max_prior_task_results :]

        # Character budget across text fields (approximate).
        budget = limits.max_characters
        user_request = _truncate(self.user_request, min(8_000, budget // 4))
        budget -= len(user_request)
        summary = None
        if self.conversation_summary:
            summary = _truncate(self.conversation_summary, min(4_000, max(0, budget // 4)))
            budget -= len(summary)

        def _trim_items(
            items: list[dict[str, Any]],
            remaining: int,
        ) -> tuple[list[dict[str, Any]], int]:
            out: list[dict[str, Any]] = []
            for item in items:
                if remaining <= 0:
                    break
                cloned = dict(item)
                for key in ("content", "summary", "text", "result_summary", "title"):
                    if key in cloned and isinstance(cloned[key], str):
                        cloned[key] = _truncate(cloned[key], min(2_000, remaining))
                        remaining -= len(cloned[key])
                out.append(cloned)
            return out, remaining

        history_out: list[dict[str, str]] = []
        for msg in history:
            if budget <= 0:
                break
            content = _truncate(str(msg.get("content", "")), min(1_500, budget))
            budget -= len(content)
            history_out.append({"role": str(msg.get("role", "user")), "content": content})

        memories, budget = _trim_items(memories, budget)
        docs, budget = _trim_items(docs, budget)
        priors, _ = _trim_items(priors, budget)

        return self.model_copy(
            update={
                "user_request": user_request,
                "conversation_summary": summary,
                "selected_history": history_out,
                "memory_context": memories,
                "document_context": docs,
                "prior_task_results": priors,
            }
        )

    def character_count(self) -> int:
        total = len(self.user_request)
        if self.conversation_summary:
            total += len(self.conversation_summary)
        for msg in self.selected_history:
            total += len(str(msg.get("content", "")))
        for items in (self.memory_context, self.document_context, self.prior_task_results):
            for item in items:
                for key in ("content", "summary", "text", "result_summary", "title"):
                    if key in item and isinstance(item[key], str):
                        total += len(item[key])
        return total
