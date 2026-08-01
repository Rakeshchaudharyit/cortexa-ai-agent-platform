"""Deterministic server-side tool selection for agent turns.

The model never chooses which tool *schemas* are attached. Only this policy
decides the allow-list; the model may then call within that allow-list.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

ConversationMode = Literal["general", "document"]

# Built-in tool names — never accept arbitrary client-supplied names.
KNOWN_TOOL_NAMES = frozenset(
    {
        "calculator",
        "current_datetime",
        "knowledge_search",
        "memory_list",
        "memory_search",
        "conversation_summary",
    }
)

_CALC_KEYWORDS = re.compile(
    r"\b("
    r"calculate|calculation|compute|arithmetic|multiply|multiplied|multiplication|"
    r"divide|divided|division|subtract|subtracted|addition|percentage|percent|"
    r"square\s+root|sqrt|convert|conversion|how\s+much\s+is|what\s+is\s+\d"
    r")\b",
    re.IGNORECASE,
)
_CALC_EXPRESSION = re.compile(
    r"(?:"
    r"\d[\d,\.]*\s*[%]|"
    r"\d[\d,\.]*\s*[+\-*/×÷^]\s*\d|"
    r"\d[\d,\.]*\s+(?:plus|minus|times|over|multiplied\s+by|divided\s+by)\s+\d|"
    r"\d[\d,\.]*\s*%\s*(?:of)\s*\d"
    r")",
    re.IGNORECASE,
)

_DATETIME_KEYWORDS = re.compile(
    r"\b("
    r"what\s+time|current\s+time|current\s+date|today'?s\s+date|what\s+date|"
    r"timezone|time\s+zone|utc|gmt|asia/\w+|america/\w+|europe/\w+|"
    r"what\s+day|day\s+of\s+the\s+week|tomorrow|yesterday|"
    r"relative\s+date|how\s+many\s+days|clock"
    r")\b",
    re.IGNORECASE,
)
_DATETIME_TZ = re.compile(r"\b[A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?\b")

_SUMMARY_KEYWORDS = re.compile(
    r"\b("
    r"summarize\s+(?:this|the|our)\s+conversation|"
    r"summarise\s+(?:this|the|our)\s+conversation|"
    r"conversation\s+summary|"
    r"summary\s+of\s+(?:this|the|our)\s+conversation|"
    r"recap\s+(?:this|the|our)\s+conversation|"
    r"tl;?dr\s+(?:this|the|our)\s+conversation"
    r")\b",
    re.IGNORECASE,
)

_MEMORY_LIST_KEYWORDS = re.compile(
    r"\b("
    r"what\s+do\s+you\s+remember|"
    r"what\s+have\s+you\s+remembered|"
    r"list\s+(?:my\s+)?memor(?:y|ies)|"
    r"show\s+(?:my\s+)?memor(?:y|ies)|"
    r"what\s+(?:preferences|facts)\s+(?:do\s+you|have\s+you)\s+(?:stored|saved|remember)"
    r")\b",
    re.IGNORECASE,
)
_MEMORY_SEARCH_KEYWORDS = re.compile(
    r"\b("
    r"search\s+(?:my\s+)?memor(?:y|ies)|"
    r"find\s+(?:in\s+)?(?:my\s+)?memor(?:y|ies)|"
    r"look\s+up\s+(?:my\s+)?memor(?:y|ies)|"
    r"do\s+you\s+remember\s+(?:about|my|that|when|if)"
    r")\b",
    re.IGNORECASE,
)

_KNOWLEDGE_EXPLICIT = re.compile(
    r"\b("
    r"search\s+(?:my\s+)?documents?|"
    r"look\s+(?:in|through)\s+(?:my\s+)?documents?|"
    r"find\s+in\s+(?:my\s+)?(?:uploaded\s+)?documents?|"
    r"knowledge\s+search|"
    r"according\s+to\s+(?:my|the)\s+(?:uploaded\s+)?documents?"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ToolSelectionContext:
    """Inputs for deterministic tool selection. No client-supplied tool names."""

    user_message: str
    conversation_mode: ConversationMode
    document_ids: list[uuid.UUID] | None
    has_accessible_documents: bool
    memory_globally_enabled: bool
    conversation_memory_enabled: bool
    registered_tool_names: frozenset[str]
    explicit_summary_operation: bool = False


@dataclass
class ToolSelectionResult:
    selected_tool_names: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)

    @property
    def tools_selected_count(self) -> int:
        return len(self.selected_tool_names)


def resolve_conversation_mode(document_ids: list[uuid.UUID] | None) -> ConversationMode:
    """General mode when document_ids is explicitly empty; otherwise document mode."""
    if document_ids is not None and len(document_ids) == 0:
        return "general"
    return "document"


def select_tools_for_turn(ctx: ToolSelectionContext) -> ToolSelectionResult:
    """Select a minimal allow-list of tool schemas for this turn."""
    text = (ctx.user_message or "").strip()
    selected: list[str] = []
    reasons: list[str] = []
    available = ctx.registered_tool_names & KNOWN_TOOL_NAMES

    def _add(name: str, reason: str) -> None:
        if name not in available:
            return
        if name in selected:
            return
        selected.append(name)
        reasons.append(reason)

    if _CALC_KEYWORDS.search(text) or _CALC_EXPRESSION.search(text):
        _add("calculator", "intent_calculator")

    if _DATETIME_KEYWORDS.search(text) or (
        _DATETIME_TZ.search(text)
        and re.search(r"\b(time|date|now|today|timezone|clock)\b", text, re.IGNORECASE)
    ):
        _add("current_datetime", "intent_datetime")

    knowledge_allowed = (
        ctx.conversation_mode == "document" or bool(_KNOWLEDGE_EXPLICIT.search(text))
    ) and ctx.has_accessible_documents
    if knowledge_allowed and "knowledge_search" in available:
        if ctx.conversation_mode == "document":
            _add("knowledge_search", "mode_document")
        else:
            _add("knowledge_search", "intent_knowledge_explicit")

    memory_active = ctx.memory_globally_enabled and ctx.conversation_memory_enabled
    if memory_active:
        if _MEMORY_LIST_KEYWORDS.search(text):
            _add("memory_list", "intent_memory_list")
        if _MEMORY_SEARCH_KEYWORDS.search(text):
            _add("memory_search", "intent_memory_search")
            # Listing is a reasonable companion for "what do you remember" style asks.
            if "memory_list" not in selected and _MEMORY_LIST_KEYWORDS.search(text):
                _add("memory_list", "intent_memory_list")
    else:
        if _MEMORY_LIST_KEYWORDS.search(text) or _MEMORY_SEARCH_KEYWORDS.search(text):
            reasons.append("memory_tools_skipped_disabled")

    if ctx.explicit_summary_operation or _SUMMARY_KEYWORDS.search(text):
        _add(
            "conversation_summary",
            "intent_summary" if not ctx.explicit_summary_operation else "explicit_summary_op",
        )

    if not selected:
        reasons.append("no_tools_needed")

    # Stable order matching known tool registry order.
    order = (
        "calculator",
        "current_datetime",
        "knowledge_search",
        "memory_list",
        "memory_search",
        "conversation_summary",
    )
    selected_sorted = [name for name in order if name in selected]
    return ToolSelectionResult(
        selected_tool_names=selected_sorted,
        reason_codes=reasons,
    )


def filter_provider_tool_names(
    *,
    candidate_names: list[str],
    registered_tool_names: frozenset[str],
) -> list[str]:
    """Hard gate: only known, registered, enabled tool names may be selected."""
    out: list[str] = []
    for name in candidate_names:
        if name not in KNOWN_TOOL_NAMES:
            continue
        if name not in registered_tool_names:
            continue
        if name not in out:
            out.append(name)
    return out
