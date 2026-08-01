"""Multi-agent orchestration exceptions."""

from __future__ import annotations


class AgentError(Exception):
    """Base error for multi-agent orchestration."""

    def __init__(self, message: str, *, code: str = "agent_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AgentRegistryError(AgentError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="agent_registry_error")


class AgentNotFoundError(AgentError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown agent '{name}'", code="agent_not_found")
        self.agent_name = name


class AgentDisabledError(AgentError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Agent '{name}' is disabled", code="agent_disabled")
        self.agent_name = name


class AgentPlanValidationError(AgentError):
    def __init__(self, message: str, *, code: str = "agent_plan_invalid") -> None:
        super().__init__(message, code=code)


class AgentStateTransitionError(AgentError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="agent_invalid_transition")


class AgentLimitExceededError(AgentError):
    def __init__(self, message: str, *, code: str = "agent_limit_exceeded") -> None:
        super().__init__(message, code=code)


class AgentOwnershipError(AgentError):
    def __init__(self, message: str = "Agent run not found or not owned") -> None:
        super().__init__(message, code="agent_ownership_denied")


class AgentApprovalError(AgentError):
    def __init__(self, message: str, *, code: str = "agent_approval_error") -> None:
        super().__init__(message, code=code)


class AgentCancelledError(AgentError):
    def __init__(self, message: str = "Agent run cancelled") -> None:
        super().__init__(message, code="agent_cancelled")


class AgentTimeoutError(AgentError):
    def __init__(self, message: str = "Agent run timed out") -> None:
        super().__init__(message, code="agent_timed_out")


class AgentSafetyError(AgentError):
    def __init__(self, message: str, *, code: str = "agent_safety_rejected") -> None:
        super().__init__(message, code=code)
