"""Agent tool-use policies and safety guards."""

from __future__ import annotations

from app.models.enums import UserRole
from app.tools.registry import ToolRegistry


def available_tool_names(registry: ToolRegistry, role: UserRole) -> set[str]:
    return {tool.name for tool in registry.list_enabled(role=role)}


def is_tool_name_allowed(registry: ToolRegistry, role: UserRole, name: str) -> bool:
    return name in available_tool_names(registry, role)
