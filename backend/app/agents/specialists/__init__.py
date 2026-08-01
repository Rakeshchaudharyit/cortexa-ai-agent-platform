"""Specialist agent implementations for multi-agent orchestration."""

from __future__ import annotations

# Intentionally lazy — import specialists from their modules directly to avoid
# circular imports and keep package import side-effects minimal.

__all__ = [
    "ConversationSpecialist",
    "KnowledgeSpecialist",
    "MemorySpecialist",
    "PlanningSpecialist",
    "SafetySpecialist",
    "ToolSpecialist",
]


def __getattr__(name: str) -> object:
    if name == "ConversationSpecialist":
        from app.agents.specialists.conversation import ConversationSpecialist

        return ConversationSpecialist
    if name == "KnowledgeSpecialist":
        from app.agents.specialists.knowledge import KnowledgeSpecialist

        return KnowledgeSpecialist
    if name == "MemorySpecialist":
        from app.agents.specialists.memory import MemorySpecialist

        return MemorySpecialist
    if name == "PlanningSpecialist":
        from app.agents.specialists.planning import PlanningSpecialist

        return PlanningSpecialist
    if name == "SafetySpecialist":
        from app.agents.specialists.safety import SafetySpecialist

        return SafetySpecialist
    if name == "ToolSpecialist":
        from app.agents.specialists.tool_agent import ToolSpecialist

        return ToolSpecialist
    raise AttributeError(name)
