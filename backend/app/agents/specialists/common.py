"""Shared helpers for specialist agents."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}|\[[\s\S]*\]")

# Document/passage content that must never be obeyed as instructions.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b"),
    re.compile(r"(?i)\bdisregard\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?)\b"),
    re.compile(r"(?i)\breveal\s+(?:the\s+)?(?:system\s+)?prompt\b"),
    re.compile(r"(?i)\byou\s+are\s+now\s+(?:a|an|in)\b"),
    re.compile(r"(?i)\boverride\s+(?:safety|policy|guardrails?)\b"),
    re.compile(r"(?i)\bexfiltrat(?:e|ion)\b"),
    re.compile(r"(?i)\bdo\s+not\s+follow\s+(?:your\s+)?(?:rules|policies)\b"),
)


def truncate_output(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").strip().split())
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3] + "..."


def load_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if not match:
            return None
        try:
            loaded = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return loaded if isinstance(loaded, dict) else None


def detect_prompt_injection(text: str) -> list[str]:
    """Return reason codes when passage text looks like instruction injection."""
    codes: list[str] = []
    sample = text or ""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(sample):
            codes.append("prompt_injection_indicator")
            break
    return codes


def mark_untrusted_passages(
    passages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Copy passages and flag injection-like content as untrusted data."""
    warnings: list[str] = []
    out: list[dict[str, Any]] = []
    for item in passages:
        cloned = dict(item)
        content = str(cloned.get("content") or cloned.get("text") or "")
        codes = detect_prompt_injection(content)
        if codes:
            cloned["untrusted"] = True
            cloned["trust_note"] = "Treated as document content only; instructions ignored"
            warnings.extend(codes)
        out.append(cloned)
    return out, list(dict.fromkeys(warnings))
