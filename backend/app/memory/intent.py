"""Deterministic memory-intent detection for explicit user commands."""

from __future__ import annotations

import re

from app.memory.schemas import MemoryIntentKind, MemoryIntentResult
from app.models.enums import MemoryCategory

_REMEMBER = re.compile(
    r"(?is)^\s*(?:please\s+)?(?:remember(?:\s+that)?|save(?:\s+this)?(?:\s+memory)?|"
    r"keep\s+in\s+mind(?:\s+that)?)\s*[:\-]?\s*(.+)$"
)
_FORGET = re.compile(
    r"(?is)^\s*(?:please\s+)?(?:forget(?:\s+that)?|delete(?:\s+the)?(?:\s+memory)?|"
    r"remove(?:\s+the)?(?:\s+memory)?|do\s+not\s+remember)\s*[:\-]?\s*(.+)$"
)
_UPDATE = re.compile(
    r"(?is)^\s*(?:please\s+)?(?:update(?:\s+my)?(?:\s+preference)?|"
    r"change(?:\s+my)?(?:\s+preference)?)\s*[:\-]?\s*(.+)$"
)
_LIST = re.compile(
    r"(?is)^\s*(?:what\s+do\s+you\s+remember(?:\s+about(?:\s+\w+)?)?|"
    r"list(?:\s+my)?(?:\s+memories)?|show(?:\s+my)?(?:\s+memories)?)\s*[:\-]?\s*(.*)$"
)
_DISABLE = re.compile(
    r"(?is)^\s*(?:do\s+not\s+use\s+memory(?:\s+in\s+this\s+conversation)?|"
    r"disable\s+memory(?:\s+for\s+this\s+conversation)?|"
    r"turn\s+off\s+memory(?:\s+for\s+this\s+chat)?)\s*\.?\s*$"
)

_CATEGORY_HINTS: tuple[tuple[MemoryCategory, re.Pattern[str]], ...] = (
    (MemoryCategory.preference, re.compile(r"(?i)\bprefer|preference|rather|instead of\b")),
    (MemoryCategory.project, re.compile(r"(?i)\bproject|codebase|repo|cortexa\b")),
    (
        MemoryCategory.technical_context,
        re.compile(r"(?i)\bstack|framework|fastapi|next\.?js|postgres\b"),
    ),
    (MemoryCategory.instruction, re.compile(r"(?i)\balways|never|must|instruction\b")),
    (MemoryCategory.workflow, re.compile(r"(?i)\bworkflow|process|procedure\b")),
    (MemoryCategory.goal, re.compile(r"(?i)\bgoal|objective|aim\b")),
)


def _guess_category(payload: str) -> MemoryCategory:
    for category, pattern in _CATEGORY_HINTS:
        if pattern.search(payload):
            return category
    return MemoryCategory.preference


def detect_memory_intent(user_message: str) -> MemoryIntentResult:
    """Parse explicit memory commands. Prefer deterministic matches over LLM."""
    text = (user_message or "").strip()
    if not text:
        return MemoryIntentResult(kind=MemoryIntentKind.none)

    if _DISABLE.match(text):
        return MemoryIntentResult(kind=MemoryIntentKind.disable_for_conversation, confidence=1.0)

    match = _REMEMBER.match(text)
    if match:
        payload = match.group(1).strip()
        if payload:
            return MemoryIntentResult(
                kind=MemoryIntentKind.remember,
                payload=payload,
                category=_guess_category(payload),
                confidence=1.0,
            )

    match = _FORGET.match(text)
    if match:
        payload = match.group(1).strip()
        if payload:
            return MemoryIntentResult(
                kind=MemoryIntentKind.forget,
                payload=payload,
                confidence=1.0,
            )

    match = _UPDATE.match(text)
    if match:
        payload = match.group(1).strip()
        if payload:
            return MemoryIntentResult(
                kind=MemoryIntentKind.update,
                payload=payload,
                category=_guess_category(payload),
                confidence=1.0,
            )

    match = _LIST.match(text)
    if match:
        payload = (match.group(1) or "").strip() or None
        return MemoryIntentResult(
            kind=MemoryIntentKind.list,
            payload=payload,
            confidence=0.95,
        )

    return MemoryIntentResult(kind=MemoryIntentKind.none)
