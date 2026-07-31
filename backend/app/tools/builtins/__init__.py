"""Built-in safe tools for Phase 6."""

from __future__ import annotations

from app.tools.builtins.calculator import CalculatorTool
from app.tools.builtins.conversation_summary import ConversationSummaryTool
from app.tools.builtins.current_datetime import CurrentDatetimeTool
from app.tools.builtins.knowledge_search import KnowledgeSearchTool
from app.tools.registry import ToolRegistry, build_default_registry


def create_builtin_tools() -> (
    list[CalculatorTool | CurrentDatetimeTool | KnowledgeSearchTool | ConversationSummaryTool]
):
    return [
        CalculatorTool(),
        CurrentDatetimeTool(),
        KnowledgeSearchTool(),
        ConversationSummaryTool(),
    ]


def create_builtin_registry() -> ToolRegistry:
    return build_default_registry(create_builtin_tools())


__all__ = [
    "CalculatorTool",
    "ConversationSummaryTool",
    "CurrentDatetimeTool",
    "KnowledgeSearchTool",
    "create_builtin_registry",
    "create_builtin_tools",
]
