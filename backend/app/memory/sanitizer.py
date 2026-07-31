"""Deterministic sanitization and sensitive-content rejection for memories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.memory.exceptions import MemorySensitiveContentError, MemoryValidationError

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAG = re.compile(r"<[^>]+>")
_SCRIPT_BLOCK = re.compile(r"(?is)<script\b[^>]*>.*?</script>")
_WHITESPACE = re.compile(r"\s+")

# Conservative credential / secret patterns — not perfect; combined with policy.
# Assignment separators include ":" "=" and natural-language "is"/"of".
_ASSIGN = r"(?:\s*[:=]\s*|\s+is\s+|\s+of\s+)"
_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(rf"(?i)\b(api[_-]?key|apikey)\b{_ASSIGN}\S+")),
    ("sk_token", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]+=*")),
    # Third segment may be short in synthetic fixtures; still treat as JWT-like.
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}\b")),
    ("password_assign", re.compile(rf"(?i)\b(password|passwd|pwd)\b{_ASSIGN}\S+")),
    (
        "secret_assign",
        re.compile(rf"(?i)\b(secret|token|private[_-]?key)\b{_ASSIGN}\S+"),
    ),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "credit_card",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    ),
    (
        "otp",
        re.compile(
            r"(?i)\b(otp|one[- ]time (?:code|password|passcode)|passcode|2fa code)\b"
            r".{0,40}\b\d{4,8}\b"
        ),
    ),
    (
        "env_secret",
        re.compile(r"(?i)\b(AWS_SECRET|DATABASE_URL|JWT_SECRET|POSTGRES_PASSWORD)\b\s*[:=]"),
    ),
)


@dataclass(frozen=True)
class SanitizedMemoryText:
    title: str
    content: str
    normalized_content: str


@dataclass(frozen=True)
class SensitivityHit:
    kind: str
    matched: bool


class MemorySanitizer:
    """Server-side sanitization — never rely only on the LLM for safety."""

    def __init__(
        self,
        *,
        max_content_characters: int = 2000,
        max_title_characters: int = 200,
    ) -> None:
        self.max_content_characters = max_content_characters
        self.max_title_characters = max_title_characters

    def normalize_whitespace(self, value: str) -> str:
        cleaned = _CONTROL_CHARS.sub("", value)
        cleaned = _SCRIPT_BLOCK.sub(" ", cleaned)
        cleaned = _HTML_TAG.sub(" ", cleaned)
        cleaned = _WHITESPACE.sub(" ", cleaned).strip()
        return cleaned

    def normalize_content(self, value: str) -> str:
        return self.normalize_whitespace(value).lower()

    def detect_sensitive(self, value: str) -> list[SensitivityHit]:
        hits: list[SensitivityHit] = []
        for kind, pattern in _SENSITIVE_PATTERNS:
            if pattern.search(value):
                # Soften credit-card false positives: require digit density.
                if kind == "credit_card":
                    digits = re.sub(r"\D", "", value)
                    if len(digits) < 13:
                        continue
                hits.append(SensitivityHit(kind=kind, matched=True))
        return hits

    def assert_not_sensitive(self, value: str) -> None:
        hits = self.detect_sensitive(value)
        if hits:
            raise MemorySensitiveContentError(
                "Memory content appears to contain secrets or sensitive data and was rejected"
            )

    def sanitize_for_storage(self, *, title: str, content: str) -> SanitizedMemoryText:
        clean_title = self.normalize_whitespace(title)
        clean_content = self.normalize_whitespace(content)
        if not clean_title:
            raise MemoryValidationError("Memory title cannot be blank", code="memory_title_empty")
        if not clean_content:
            raise MemoryValidationError(
                "Memory content cannot be blank",
                code="memory_content_empty",
            )
        if len(clean_title) > self.max_title_characters:
            raise MemoryValidationError(
                f"Memory title exceeds {self.max_title_characters} characters",
                code="memory_title_too_long",
            )
        if len(clean_content) > self.max_content_characters:
            raise MemoryValidationError(
                f"Memory content exceeds {self.max_content_characters} characters",
                code="memory_content_too_long",
            )
        self.assert_not_sensitive(f"{clean_title}\n{clean_content}")
        normalized = self.normalize_content(clean_content)
        if len(normalized) > 2000:
            normalized = normalized[:2000]
        return SanitizedMemoryText(
            title=clean_title,
            content=clean_content,
            normalized_content=normalized,
        )

    def redact_for_audit(self, value: str | None, *, max_len: int = 40) -> str | None:
        if value is None:
            return None
        # Never persist raw content in audits — only a safe length hint.
        length = len(value)
        return f"[redacted length={min(length, max_len)}]"

    def redact_value(self, value: str) -> str:
        redacted = value
        for _kind, pattern in _SENSITIVE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
