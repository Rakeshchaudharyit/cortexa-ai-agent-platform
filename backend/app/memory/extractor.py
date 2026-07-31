"""Conservative memory extraction from completed conversation turns."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import Settings
from app.llm.schemas import ChatMessage, GenerateRequest, MessageRole
from app.memory.policies import EXTRACTABLE_CATEGORIES
from app.memory.prompts import MEMORY_EXTRACTION_SYSTEM, build_extraction_user_prompt
from app.memory.sanitizer import MemorySanitizer
from app.memory.schemas import MemoryCandidate
from app.models.enums import MemoryCategory, MemoryConfidence
from app.services.llm import LLMService

logger = logging.getLogger("cortexa.memory.extractor")

_TRANSIENT = re.compile(r"(?i)^\s*(hi|hello|hey|thanks|thank you|ok|okay|test|ping)\b")
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class MemoryExtractor:
    """Produce structured memory candidates; treat model output as untrusted."""

    def __init__(
        self,
        settings: Settings,
        llm_service: LLMService | None = None,
        sanitizer: MemorySanitizer | None = None,
    ) -> None:
        self.settings = settings
        self.llm_service = llm_service
        self.sanitizer = sanitizer or MemorySanitizer(
            max_content_characters=settings.memory_max_content_characters,
            max_title_characters=settings.memory_title_max_characters,
        )

    async def extract_from_turn(
        self,
        *,
        user_content: str,
        assistant_content: str,
    ) -> list[MemoryCandidate]:
        user_text = (user_content or "").strip()
        assistant_text = (assistant_content or "").strip()
        if not user_text or _TRANSIENT.match(user_text):
            return []

        # Prefer durable preference heuristics before calling the LLM.
        heuristic = self._heuristic_candidates(user_text)
        if heuristic:
            return heuristic

        if self.llm_service is None:
            return []

        try:
            response = await self.llm_service.generate(
                GenerateRequest(
                    messages=[
                        ChatMessage(
                            role=MessageRole.user,
                            content=build_extraction_user_prompt(
                                user_content=user_text,
                                assistant_content=assistant_text,
                            ),
                        )
                    ],
                    system=MEMORY_EXTRACTION_SYSTEM,
                    temperature=0.0,
                    max_tokens=800,
                )
            )
        except Exception:
            logger.info("memory_extraction_provider_failed")
            return []

        return self._parse_candidates(response.content)

    def _heuristic_candidates(self, user_text: str) -> list[MemoryCandidate]:
        """Deterministic extraction for clear preference/project statements."""
        lowered = user_text.lower()
        candidates: list[MemoryCandidate] = []

        prefer = re.search(
            r"(?i)\bi\s+(?:prefer|like|want)\s+(.+?)(?:\.|$)",
            user_text,
        )
        if prefer:
            payload = prefer.group(1).strip()
            if payload and not self.sanitizer.detect_sensitive(payload):
                candidates.append(
                    MemoryCandidate(
                        title="User preference",
                        content=f"The user prefers {payload}.",
                        category=MemoryCategory.preference,
                        confidence=MemoryConfidence.high,
                        importance=0.8,
                        reason="Explicit preference statement",
                    )
                )

        timezone = re.search(
            r"(?i)\b(?:timezone|time zone)\s+(?:is\s+)?([A-Za-z_]+/[A-Za-z_]+)\b",
            user_text,
        )
        if timezone:
            tz = timezone.group(1)
            candidates.append(
                MemoryCandidate(
                    title="Timezone preference",
                    content=f"The user's default timezone is {tz}.",
                    category=MemoryCategory.preference,
                    confidence=MemoryConfidence.high,
                    importance=0.7,
                    reason="Explicit timezone",
                )
            )

        if "working on" in lowered or "project uses" in lowered:
            snippet = user_text.strip()
            if len(snippet) <= self.settings.memory_max_content_characters:
                if not self.sanitizer.detect_sensitive(snippet):
                    candidates.append(
                        MemoryCandidate(
                            title="Project context",
                            content=snippet,
                            category=MemoryCategory.project,
                            confidence=MemoryConfidence.medium,
                            importance=0.6,
                            reason="Project context statement",
                        )
                    )
        return candidates

    def _parse_candidates(self, raw: str) -> list[MemoryCandidate]:
        payload = self._load_json(raw)
        if not isinstance(payload, dict):
            return []
        items = payload.get("candidates")
        if not isinstance(items, list):
            return []
        results: list[MemoryCandidate] = []
        for item in items[:5]:
            candidate = self._coerce_candidate(item)
            if candidate is None:
                continue
            if candidate.sensitive:
                continue
            if candidate.category not in EXTRACTABLE_CATEGORIES:
                continue
            if self.sanitizer.detect_sensitive(f"{candidate.title}\n{candidate.content}"):
                continue
            try:
                cleaned = self.sanitizer.sanitize_for_storage(
                    title=candidate.title,
                    content=candidate.content,
                )
            except Exception:
                continue
            results.append(
                candidate.model_copy(
                    update={
                        "title": cleaned.title,
                        "content": cleaned.content,
                    }
                )
            )
        return results

    def _load_json(self, raw: str) -> Any:
        text = (raw or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_BLOCK.search(text)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    def _coerce_candidate(self, item: Any) -> MemoryCandidate | None:
        if not isinstance(item, dict):
            return None
        try:
            category_raw = str(item.get("category") or "other").strip().lower()
            confidence_raw = str(item.get("confidence") or "medium").strip().lower()
            category = MemoryCategory(category_raw)
            confidence = MemoryConfidence(confidence_raw)
            return MemoryCandidate(
                title=str(item.get("title") or "Memory").strip()[:200],
                content=str(item.get("content") or "").strip(),
                category=category,
                confidence=confidence,
                importance=float(item.get("importance") or 0.5),
                reason=str(item.get("reason") or "")[:500],
                sensitive=bool(item.get("sensitive")),
            )
        except Exception:
            return None
