"""Phase 9.5 content-free orchestration telemetry tests."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.budgets import RunBudget
from app.agents.telemetry import PhaseTimer, apply_budget_snapshot, calculate_execution_duration_ms


def test_apply_budget_snapshot_copies_only_numeric_counters() -> None:
    budget = RunBudget(
        maximum_steps=12,
        max_llm_calls=8,
        max_tool_calls=4,
        max_context_characters=10_000,
        run_timeout_seconds=120,
        steps_used=3,
        llm_calls_used=2,
        tool_calls_used=1,
        context_characters=875,
    )
    run = SimpleNamespace(
        steps_used=0,
        llm_calls_used=0,
        tool_calls_used=0,
        context_characters_used=0,
    )

    apply_budget_snapshot(run, budget)

    assert run.steps_used == 3
    assert run.llm_calls_used == 2
    assert run.tool_calls_used == 1
    assert run.context_characters_used == 875
    assert not hasattr(run, "prompt")


def test_apply_budget_snapshot_never_persists_negative_values() -> None:
    budget = RunBudget(
        maximum_steps=1,
        max_llm_calls=1,
        max_tool_calls=1,
        max_context_characters=1,
        run_timeout_seconds=1,
        steps_used=-1,
        llm_calls_used=-2,
        tool_calls_used=-3,
        context_characters=-4,
    )
    run = SimpleNamespace()

    apply_budget_snapshot(run, budget)

    assert (run.steps_used, run.llm_calls_used, run.tool_calls_used) == (0, 0, 0)
    assert run.context_characters_used == 0


def test_execution_duration_is_sum_of_bounded_task_durations() -> None:
    run = SimpleNamespace(
        tasks=[
            SimpleNamespace(duration_ms=125),
            SimpleNamespace(duration_ms=None),
            SimpleNamespace(duration_ms=-50),
            SimpleNamespace(duration_ms=75),
        ]
    )
    assert calculate_execution_duration_ms(run) == 200


def test_phase_timer_returns_non_negative_integer() -> None:
    assert isinstance(PhaseTimer().elapsed_ms(), int)
    assert PhaseTimer().elapsed_ms() >= 0


def test_run_budget_bounded_timeout_never_exceeds_run_deadline() -> None:
    budget = RunBudget(
        maximum_steps=4,
        max_llm_calls=4,
        max_tool_calls=2,
        max_context_characters=1000,
        run_timeout_seconds=30.0,
    )

    assert 0.0 < budget.bounded_timeout(120.0) <= 30.0
    assert budget.bounded_timeout(5.0) <= 5.0
