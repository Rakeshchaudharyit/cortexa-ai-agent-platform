"""Explicit state machines for agent runs, tasks, and approvals."""

from __future__ import annotations

from app.agents.exceptions import AgentStateTransitionError
from app.models.enums import AgentApprovalStatus, AgentRunStatus, AgentTaskStatus

AGENT_RUN_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.pending: frozenset(
        {
            AgentRunStatus.planning,
            AgentRunStatus.running,  # single-agent shortcut
            AgentRunStatus.failed,
            AgentRunStatus.cancelled,
        }
    ),
    AgentRunStatus.planning: frozenset(
        {
            AgentRunStatus.running,
            AgentRunStatus.failed,
            AgentRunStatus.cancelled,
            AgentRunStatus.timed_out,
        }
    ),
    AgentRunStatus.running: frozenset(
        {
            AgentRunStatus.awaiting_approval,
            AgentRunStatus.completed,
            AgentRunStatus.failed,
            AgentRunStatus.cancelled,
            AgentRunStatus.timed_out,
        }
    ),
    AgentRunStatus.awaiting_approval: frozenset(
        {
            AgentRunStatus.running,
            AgentRunStatus.cancelled,
            AgentRunStatus.failed,
            AgentRunStatus.timed_out,
        }
    ),
    AgentRunStatus.completed: frozenset(),
    AgentRunStatus.failed: frozenset(),
    AgentRunStatus.cancelled: frozenset(),
    AgentRunStatus.timed_out: frozenset(),
}

AGENT_TASK_TRANSITIONS: dict[AgentTaskStatus, frozenset[AgentTaskStatus]] = {
    AgentTaskStatus.pending: frozenset(
        {
            AgentTaskStatus.ready,
            AgentTaskStatus.running,
            AgentTaskStatus.skipped,
            AgentTaskStatus.cancelled,
            AgentTaskStatus.failed,
        }
    ),
    AgentTaskStatus.ready: frozenset(
        {
            AgentTaskStatus.running,
            AgentTaskStatus.awaiting_approval,
            AgentTaskStatus.skipped,
            AgentTaskStatus.cancelled,
            AgentTaskStatus.failed,
        }
    ),
    AgentTaskStatus.running: frozenset(
        {
            AgentTaskStatus.awaiting_approval,
            AgentTaskStatus.succeeded,
            AgentTaskStatus.failed,
            AgentTaskStatus.skipped,
            AgentTaskStatus.cancelled,
            AgentTaskStatus.timed_out,
            AgentTaskStatus.ready,  # retry after transient failure
        }
    ),
    AgentTaskStatus.awaiting_approval: frozenset(
        {
            AgentTaskStatus.running,
            AgentTaskStatus.skipped,
            AgentTaskStatus.cancelled,
            AgentTaskStatus.failed,
            AgentTaskStatus.timed_out,
        }
    ),
    AgentTaskStatus.succeeded: frozenset(),
    AgentTaskStatus.failed: frozenset(),
    AgentTaskStatus.skipped: frozenset(),
    AgentTaskStatus.cancelled: frozenset(),
    AgentTaskStatus.timed_out: frozenset(),
}

AGENT_APPROVAL_TRANSITIONS: dict[AgentApprovalStatus, frozenset[AgentApprovalStatus]] = {
    AgentApprovalStatus.pending: frozenset(
        {
            AgentApprovalStatus.approved,
            AgentApprovalStatus.rejected,
            AgentApprovalStatus.expired,
            AgentApprovalStatus.cancelled,
        }
    ),
    AgentApprovalStatus.approved: frozenset(),
    AgentApprovalStatus.rejected: frozenset(),
    AgentApprovalStatus.expired: frozenset(),
    AgentApprovalStatus.cancelled: frozenset(),
}

TERMINAL_RUN_STATUSES: frozenset[AgentRunStatus] = frozenset(
    {
        AgentRunStatus.completed,
        AgentRunStatus.failed,
        AgentRunStatus.cancelled,
        AgentRunStatus.timed_out,
    }
)

TERMINAL_TASK_STATUSES: frozenset[AgentTaskStatus] = frozenset(
    {
        AgentTaskStatus.succeeded,
        AgentTaskStatus.failed,
        AgentTaskStatus.skipped,
        AgentTaskStatus.cancelled,
        AgentTaskStatus.timed_out,
    }
)


def is_terminal_run(status: AgentRunStatus) -> bool:
    return status in TERMINAL_RUN_STATUSES


def is_terminal_task(status: AgentTaskStatus) -> bool:
    return status in TERMINAL_TASK_STATUSES


def validate_run_transition(current: AgentRunStatus, target: AgentRunStatus) -> None:
    if current == target and current in TERMINAL_RUN_STATUSES:
        # Idempotent terminal no-op is allowed by callers; reject non-terminal self.
        return
    allowed = AGENT_RUN_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise AgentStateTransitionError(
            f"Invalid agent run transition: {current.value} → {target.value}"
        )


def validate_task_transition(current: AgentTaskStatus, target: AgentTaskStatus) -> None:
    if current == target and current in TERMINAL_TASK_STATUSES:
        return
    allowed = AGENT_TASK_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise AgentStateTransitionError(
            f"Invalid agent task transition: {current.value} → {target.value}"
        )


def validate_approval_transition(
    current: AgentApprovalStatus,
    target: AgentApprovalStatus,
) -> None:
    if current == target and current != AgentApprovalStatus.pending:
        return
    allowed = AGENT_APPROVAL_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise AgentStateTransitionError(
            f"Invalid approval transition: {current.value} → {target.value}"
        )
