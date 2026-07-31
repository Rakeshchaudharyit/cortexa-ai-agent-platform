"""Tool registry unit tests."""

from __future__ import annotations

import pytest
from app.models.enums import UserRole
from app.tools.builtins import CalculatorTool, create_builtin_registry
from app.tools.builtins.calculator import CalculatorTool as Calc
from app.tools.exceptions import ToolNotFoundError, ToolRegistryError
from app.tools.registry import ToolRegistry, build_default_registry


def test_registers_valid_tools() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    assert registry.get("calculator").name == "calculator"


def test_rejects_duplicates() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    with pytest.raises(ToolRegistryError, match="Duplicate"):
        registry.register(CalculatorTool())


def test_rejects_invalid_names() -> None:
    class BadTool(Calc):
        name = "Bad-Name"  # type: ignore[misc]

    registry = ToolRegistry()
    with pytest.raises(ToolRegistryError, match="Invalid tool name"):
        registry.register(BadTool())


def test_lists_tools_deterministically() -> None:
    registry = create_builtin_registry()
    names = [tool.name for tool in registry.list_all()]
    assert names == sorted(names)
    assert names == [
        "calculator",
        "conversation_summary",
        "current_datetime",
        "knowledge_search",
        "memory_list",
        "memory_search",
    ]


def test_filters_by_role() -> None:
    registry = create_builtin_registry()
    user_tools = registry.list_enabled(role=UserRole.user)
    assert {t.name for t in user_tools} == {
        "calculator",
        "conversation_summary",
        "current_datetime",
        "knowledge_search",
        "memory_list",
        "memory_search",
    }


def test_provider_schemas_valid() -> None:
    registry = create_builtin_registry()
    schemas = registry.provider_schemas(role=UserRole.user)
    assert schemas
    for spec in schemas:
        assert spec.name
        assert spec.description
        assert isinstance(spec.parameters, dict)


def test_unregister_and_clear() -> None:
    registry = build_default_registry([CalculatorTool()])
    registry.unregister("calculator")
    with pytest.raises(ToolNotFoundError):
        registry.get("calculator")
    registry.register(CalculatorTool())
    registry.clear()
    assert registry.names() == []
