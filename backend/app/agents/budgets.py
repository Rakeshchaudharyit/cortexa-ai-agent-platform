"""Run-level budget accounting for multi-agent execution."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.agents.exceptions import AgentLimitExceededError, AgentTimeoutError


@dataclass
class RunBudget:
    """Pre-flight budget checks for steps, LLM/tool calls, context, and duration."""

    maximum_steps: int
    max_llm_calls: int
    max_tool_calls: int
    max_context_characters: int
    run_timeout_seconds: float
    steps_used: int = 0
    llm_calls_used: int = 0
    tool_calls_used: int = 0
    context_characters: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    @property
    def duration_ms(self) -> int:
        return int(self.elapsed_seconds * 1000)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.run_timeout_seconds - self.elapsed_seconds)

    def bounded_timeout(self, requested_seconds: float, *, floor_seconds: float = 0.1) -> float:
        """Return a timeout that cannot outlive the run-level deadline."""
        self.check_run_timeout()
        return max(floor_seconds, min(float(requested_seconds), self.remaining_seconds))

    def check_run_timeout(self) -> None:
        if self.elapsed_seconds > self.run_timeout_seconds:
            raise AgentTimeoutError("Agent run timed out")

    def require_step(self) -> None:
        self.check_run_timeout()
        if self.steps_used >= self.maximum_steps:
            raise AgentLimitExceededError(
                "Agent run exceeded maximum steps",
                code="agent_steps_exceeded",
            )

    def consume_step(self) -> None:
        self.require_step()
        self.steps_used += 1

    def require_llm(self, count: int = 1) -> None:
        self.check_run_timeout()
        if self.llm_calls_used + count > self.max_llm_calls:
            raise AgentLimitExceededError(
                "Agent run exceeded maximum LLM calls",
                code="agent_llm_budget_exceeded",
            )

    def consume_llm(self, count: int = 1) -> None:
        self.require_llm(count)
        self.llm_calls_used += count

    def require_tools(self, count: int = 1) -> None:
        self.check_run_timeout()
        if self.tool_calls_used + count > self.max_tool_calls:
            raise AgentLimitExceededError(
                "Agent run exceeded maximum tool calls",
                code="agent_tool_budget_exceeded",
            )

    def consume_tools(self, count: int = 1) -> None:
        self.require_tools(count)
        self.tool_calls_used += count

    def observe_context(self, characters: int) -> None:
        self.context_characters = max(self.context_characters, characters)
        if characters > self.max_context_characters:
            raise AgentLimitExceededError(
                "Agent context character budget exceeded",
                code="agent_context_budget_exceeded",
            )

    def snapshot(self) -> dict[str, int | float]:
        return {
            "steps_used": self.steps_used,
            "llm_calls_used": self.llm_calls_used,
            "tool_calls_used": self.tool_calls_used,
            "context_characters": self.context_characters,
            "duration_ms": self.duration_ms,
        }
