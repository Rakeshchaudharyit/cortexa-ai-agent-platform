"""Deterministic conversation context builder with trimming and RAG prioritization.

Priority (highest first):
1. current user message
2. retrieved RAG context
3. recent conversation messages
4. conversation summary
5. oldest messages trimmed first
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.llm.schemas import ChatMessage
from app.llm.schemas import MessageRole as LLMMessageRole
from app.models.conversation import Message
from app.models.enums import MessageRole, MessageStatus
from app.services.retrieval import RetrievedChunk

_RAG_SYSTEM_PROMPT = (
    "You are a grounded conversational assistant for the user's private documents. "
    "Answer using ONLY the provided context and conversation history. "
    "Answer directly and concisely in one or two short sentences. "
    "Do not repeat the question. "
    'Do not write filler such as "According to the document" more than once, '
    "and prefer answering without that phrase. "
    "Cite supporting passages ONLY with bracket markers such as [1], [2]. "
    "Do NOT invent facts, filenames, or citations. "
    'Do NOT write source-detail lines, filenames, "Source:", "Citation ID", '
    "or duplicate citation metadata in the answer prose — the UI shows citations separately. "
    "If the answer is not present in the context, say clearly that you could not find it "
    "in the selected documents and do not invent an answer or citation."
)

_GENERAL_SYSTEM_PROMPT = (
    "You are a helpful conversational assistant. Use the conversation history to answer. "
    "Be concise and accurate. Do not invent document citations."
)


@dataclass(frozen=True)
class BuiltContext:
    messages: list[ChatMessage]
    system: str
    history_message_count: int
    history_character_count: int
    rag_character_count: int
    memory_character_count: int
    included_summary: bool
    trimmed: bool


@dataclass
class ConversationContextBuilder:
    """Build bounded LLM context for multi-turn chat."""

    settings: Settings

    def build(
        self,
        *,
        current_user_content: str,
        history_messages: list[Message],
        summary: str | None,
        retrieved: list[RetrievedChunk],
        general_mode: bool = False,
        memory_context: str | None = None,
    ) -> BuiltContext:
        max_history_messages = self.settings.conversation_max_history_messages
        max_history_chars = self.settings.conversation_max_history_characters
        max_context_chars = self.settings.conversation_max_context_characters
        max_rag_chars = self.settings.rag_max_context_characters

        eligible = [
            message
            for message in history_messages
            if message.is_active
            and message.status == MessageStatus.complete
            and message.role in {MessageRole.user, MessageRole.assistant}
            and message.content.strip()
        ]

        rag_context = self._build_rag_context(retrieved, max_chars=max_rag_chars)
        memory_block = (memory_context or "").strip()
        current = current_user_content.strip()

        selected: list[Message] = []
        history_chars = 0
        trimmed = False
        for message in reversed(eligible):
            if len(selected) >= max_history_messages:
                trimmed = True
                break
            length = len(message.content)
            if history_chars + length > max_history_chars and selected:
                trimmed = True
                break
            selected.append(message)
            history_chars += length
        selected.reverse()

        included_summary = bool(summary and summary.strip() and trimmed)
        summary_text = (summary or "").strip() if included_summary else ""
        if summary_text:
            summary_text = summary_text[: self.settings.conversation_summary_max_characters]

        system = _GENERAL_SYSTEM_PROMPT if general_mode else _RAG_SYSTEM_PROMPT
        if memory_block:
            system = f"{system}\n\n{memory_block}"

        chat_messages: list[ChatMessage] = []

        reserved = (
            len(current)
            + len(rag_context)
            + len(memory_block)
            + (len(summary_text) + 64 if summary_text else 0)
        )
        remaining = max_context_chars - reserved
        if remaining < 0:
            summary_text = ""
            included_summary = False
            remaining = max_context_chars - len(current) - len(rag_context) - len(memory_block)
            if remaining < 0 and rag_context:
                rag_context = rag_context[
                    : max(0, max_context_chars - len(current) - len(memory_block) - 32)
                ]
                remaining = max_context_chars - len(current) - len(rag_context) - len(memory_block)

        packed_history: list[Message] = []
        used = 0
        for message in reversed(selected):
            length = len(message.content)
            if used + length > remaining and packed_history:
                trimmed = True
                break
            if used + length > remaining:
                trimmed = True
                break
            packed_history.append(message)
            used += length
        packed_history.reverse()

        if summary_text:
            chat_messages.append(
                ChatMessage(
                    role=LLMMessageRole.user,
                    content=f"Conversation summary so far:\n{summary_text}",
                )
            )
            chat_messages.append(
                ChatMessage(
                    role=LLMMessageRole.assistant,
                    content="Understood. I will use the summary for earlier context.",
                )
            )

        for message in packed_history:
            role = (
                LLMMessageRole.user
                if message.role == MessageRole.user
                else LLMMessageRole.assistant
            )
            chat_messages.append(ChatMessage(role=role, content=message.content))

        if rag_context:
            user_payload = f"Context:\n{rag_context}\n\nQuestion:\n{current}"
        else:
            user_payload = current
        chat_messages.append(ChatMessage(role=LLMMessageRole.user, content=user_payload))

        return BuiltContext(
            messages=chat_messages,
            system=system,
            history_message_count=len(packed_history),
            history_character_count=sum(len(m.content) for m in packed_history),
            rag_character_count=len(rag_context),
            memory_character_count=len(memory_block),
            included_summary=included_summary,
            trimmed=trimmed,
        )

    def _build_rag_context(self, retrieved: list[RetrievedChunk], *, max_chars: int) -> str:
        if not retrieved:
            return ""
        parts: list[str] = []
        used = 0
        for index, item in enumerate(retrieved, start=1):
            # Keep headers minimal so the model cites [n] without echoing filenames.
            header = f"[{index}]"
            body = item.chunk.content.strip()
            block = f"{header}\n{body}"
            separator = 2 if parts else 0
            if used + separator + len(block) > max_chars:
                remaining = max_chars - used - separator
                if remaining < 40:
                    break
                parts.append(block[:remaining])
                break
            parts.append(block)
            used += separator + len(block)
        return "\n\n".join(parts)
