"""Deterministic tool registry — no fragile process-global mutation required."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.models.enums import UserRole
from app.tools.base import BaseTool
from app.tools.exceptions import ToolNotFoundError, ToolRegistryError
from app.tools.schemas import ToolSpec

_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


@dataclass(frozen=True)
class ToolRuntimeOverride:
    """Admin/runtime override for a registered tool (does not mutate ClassVars)."""

    enabled: bool | None = None
    timeout_seconds: int | None = None
    confirmation_required: bool | None = None


class ToolRegistry:
    """In-memory registry of server-approved tools.

    Create a fresh instance per application (or per test). Avoid relying on a
    mutable module-level singleton for test isolation.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._overrides: dict[str, ToolRuntimeOverride] = {}

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
        self._overrides.pop(name, None)

    def clear(self) -> None:
        self._tools.clear()
        self._overrides.clear()

    def apply_overrides(self, overrides: dict[str, ToolRuntimeOverride]) -> None:
        """Replace runtime overrides (typically loaded from ToolConfiguration rows)."""
        self._overrides = dict(overrides)

    def clear_overrides(self) -> None:
        self._overrides.clear()

    def get_override(self, name: str) -> ToolRuntimeOverride | None:
        return self._overrides.get(name)

    def is_effectively_enabled(self, tool: BaseTool) -> bool:
        override = self._overrides.get(tool.name)
        if override is not None and override.enabled is not None:
            return override.enabled
        return bool(tool.enabled)

    def effective_timeout(self, tool: BaseTool) -> int:
        override = self._overrides.get(tool.name)
        if override is not None and override.timeout_seconds is not None:
            return int(override.timeout_seconds)
        return int(tool.timeout_seconds)

    def effective_confirmation_required(self, tool: BaseTool) -> bool:
        override = self._overrides.get(tool.name)
        if override is not None and override.confirmation_required is not None:
            return bool(override.confirmation_required)
        return bool(tool.requires_confirmation)

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
            if not self.is_effectively_enabled(tool):
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
