"""Safe, passive telemetry helpers for multi-agent orchestration.

Telemetry must never receive prompt bodies, retrieved passages, memory values,
tool arguments, credentials, or provider payloads.  It records bounded numeric
execution metadata only and cannot control run state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.budgets import RunBudget
    from app.models.agent import AgentRun


@dataclass
class PhaseTimer:
    """Monotonic timer suitable for one orchestration phase."""

    started_monotonic: float = field(default_factory=time.monotonic)

    def elapsed_ms(self) -> int:
        return max(0, int((time.monotonic() - self.started_monotonic) * 1000))


def apply_budget_snapshot(run: AgentRun, budget: RunBudget) -> None:
    """Copy durable counters from a run budget without affecting execution."""

    run.steps_used = max(0, budget.steps_used)
    run.llm_calls_used = max(0, budget.llm_calls_used)
    run.tool_calls_used = max(0, budget.tool_calls_used)
    run.context_characters_used = max(0, budget.context_characters)


def calculate_execution_duration_ms(run: AgentRun) -> int:
    """Return the bounded sum of completed task durations."""

    return sum(max(0, task.duration_ms or 0) for task in getattr(run, "tasks", []))
