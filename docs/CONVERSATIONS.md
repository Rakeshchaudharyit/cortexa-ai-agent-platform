# Conversations & Streaming Chat

Cortexa provides persistent, user-owned conversations with multi-turn chat, optional document retrieval, streaming responses, citations, edit/regenerate flows, and conversation history.

## Modes

### General Chat

Retrieval is intentionally disabled and the configured LLM answers without document grounding.

### Document Knowledge

The conversation uses eligible owner-scoped document versions, returns structured citation snapshots, and applies the RAG no-answer policy when suitable context is unavailable.

## Message lifecycle

1. Validate the active conversation and user ownership.
2. Persist the user message.
3. Create the assistant response record.
4. Retrieve eligible RAG context when requested.
5. Build bounded context from the current message, history, optional summary, memory and RAG passages.
6. Stream model output to the browser.
7. Persist final assistant content, provider/model metadata, timing and citations.
8. Optionally update title/summary metadata.

## Streaming

The frontend uses `fetch` + `ReadableStream`, allowing bearer authorization while consuming SSE-style event frames. The stream can include:

- start/lifecycle metadata;
- content deltas;
- citation events;
- safe tool/memory activity events where enabled;
- final completion metadata;
- controlled error events.

Raw model-provider payloads and hidden reasoning are not forwarded to the client.

## Edit and regenerate

Editing a user turn supersedes later active turns according to the existing conversation model. Regeneration creates a replacement assistant response from the latest active user turn while preserving conversation ownership and persistence rules.

## Persistence

Conversation, message and citation records are stored in PostgreSQL. Citation snapshots preserve the source context associated with a historical answer even when document metadata changes later.
