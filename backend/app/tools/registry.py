"""Deterministic tool registry — no fragile process-global mutation required."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.models.enums import UserRole
from app.tools.base import BaseTool
from app.tools.exceptions import ToolNotFoundError, ToolRegistryError
from app.tools.schemas import ToolSpec

_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


class ToolRegistry:
    """In-memory registry of server-approved tools.

    Create a fresh instance per application (or per test). Avoid relying on a
    mutable module-level singleton for test isolation.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.name
        if not _TOOL_NAME_RE.match(name):
            raise ToolRegistryError(
                f"Invalid tool name '{name}': must match {_TOOL_NAME_RE.pattern}"
            )
        if name in self._tools:
            raise ToolRegistryError(f"Duplicate tool name '{name}'")
        self._tools[name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def clear(self) -> None:
        self._tools.clear()

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_all(self) -> list[BaseTool]:
        return [self._tools[name] for name in sorted(self._tools)]

    def list_enabled(self, *, role: UserRole | None = None) -> list[BaseTool]:
        tools: list[BaseTool] = []
        for tool in self.list_all():
            if not tool.enabled:
                continue
            if role is not None and not tool.is_allowed_for_role(role):
                continue
            tools.append(tool)
        return tools

    def provider_schemas(self, *, role: UserRole | None = None) -> list[ToolSpec]:
        return [tool.to_spec() for tool in self.list_enabled(role=role)]

    def names(self) -> list[str]:
        return sorted(self._tools)


def build_default_registry(tools: Iterable[BaseTool] | None = None) -> ToolRegistry:
    """Build a registry, optionally pre-loading tools."""
    registry = ToolRegistry()
    if tools is not None:
        for tool in tools:
            registry.register(tool)
    return registry
