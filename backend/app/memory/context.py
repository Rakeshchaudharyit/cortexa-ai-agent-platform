"""Memory context block builder — separate from RAG and conversation history."""

from __future__ import annotations

from app.memory.prompts import format_memory_context
from app.memory.schemas import MemoryContextBlock, RetrievedMemoryView


def build_memory_context_block(
    memories: list[RetrievedMemoryView],
    *,
    max_characters: int,
) -> MemoryContextBlock:
    if not memories:
        return MemoryContextBlock(text="", memory_ids=[], count=0, character_count=0)

    selected: list[RetrievedMemoryView] = []
    for memory in memories:
        trial = selected + [memory]
        text = format_memory_context(trial)
        if selected and len(text) > max_characters:
            break
        if not selected and len(text) > max_characters:
            # Always try to include at least one truncated memory.
            truncated = memory.model_copy(
                update={"content": memory.content[: max(40, max_characters - 120)]}
            )
            selected = [truncated]
            break
        selected.append(memory)

    text = format_memory_context(selected)
    if len(text) > max_characters:
        text = text[:max_characters]
    return MemoryContextBlock(
        text=text,
        memory_ids=[m.id for m in selected],
        count=len(selected),
        character_count=len(text),
    )
