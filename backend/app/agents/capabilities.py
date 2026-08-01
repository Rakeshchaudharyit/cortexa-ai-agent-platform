"""Agent capability identifiers and helpers."""

from __future__ import annotations

from enum import StrEnum


class AgentCapability(StrEnum):
    """Declared capabilities for registered system agents."""

    classify = "classify"
    dispatch = "dispatch"
    enforce_limits = "enforce_limits"
    combine_results = "combine_results"
    cancel = "cancel"
    decompose = "decompose"
    structure_plan = "structure_plan"
    identify_approvals = "identify_approvals"
    chat = "chat"
    synthesize = "synthesize"
    fallback = "fallback"
    retrieve_documents = "retrieve_documents"
    cite = "cite"
    summarize_context = "summarize_context"
    retrieve_memories = "retrieve_memories"
    explicit_memory_write = "explicit_memory_write"
    list_memories = "list_memories"
    execute_tools = "execute_tools"
    validate_arguments = "validate_arguments"
    validate_plan = "validate_plan"
    detect_injection = "detect_injection"
    require_approval = "require_approval"
    reject_unauthorized = "reject_unauthorized"


# Agents that must remain enabled whenever multi-agent mode is active.
REQUIRED_MULTI_AGENT_KEYS: frozenset[str] = frozenset({"coordinator", "safety"})

# Known system agent keys — models cannot invent names outside this set.
SYSTEM_AGENT_KEYS: frozenset[str] = frozenset(
    {
        "coordinator",
        "planning",
        "conversation",
        "knowledge",
        "memory",
        "tool",
        "safety",
    }
)
