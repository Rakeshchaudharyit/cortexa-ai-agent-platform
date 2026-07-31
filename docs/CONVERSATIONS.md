# Conversations & Multi-Turn Chat (Phase 5)

Phase 5 adds **persistent, user-owned conversations** with multi-turn RAG chat, SSE streaming, edit/regenerate flows, rolling summaries, and a Next.js `/chat` UI. It builds on Phase 4 documents and retrieval; it is **not** cross-conversation memory or org-wide shared chat.

**Phase 6** extends the same chat flow with optional agent tools (see [AGENT_TOOLS.md](AGENT_TOOLS.md)). When `AGENT_TOOLS_ENABLED=true`, the orchestrator may emit additional SSE tool events while preserving `start` / `delta` / `citation` / `complete` compatibility.

**Phase 7** may also emit memory lifecycle SSE events (`memory_retrieval_*`, `memory_saved`, `memory_candidate_proposed`, …) and inject a bounded memory context block into the system prompt. See [LONG_TERM_MEMORY.md](LONG_TERM_MEMORY.md).

See also: [RAG.md](RAG.md), [AUTHENTICATION.md](AUTHENTICATION.md), [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Data model

### `Conversation`

| Field | Purpose |
| --- | --- |
| `id`, `user_id` | UUID primary key; FK to `users` (CASCADE delete) |
| `title`, `title_is_auto` | Display title; auto-generated titles stay flagged until the user renames |
| `status` | `active` or `archived` |
| `message_count`, `last_message_at` | Denormalized list/sort helpers |
| `summary`, `summary_updated_at` | Rolling text summary for long threads (see below) |
| `default_document_scope` | Optional JSONB list of document UUIDs stored on create |
| `metadata` | JSONB bag (ORM: `conversation_metadata`) |
| `created_at`, `updated_at`, `archived_at` | Timestamps |

### `Message`

| Field | Purpose |
| --- | --- |
| `conversation_id`, `user_id` | Ownership and cascade delete with conversation |
| `role` | `user`, `assistant`, or `system` |
| `content`, `status` | Text; `pending` → `complete` or `failed` for assistants |
| `sequence_number` | Strict per-conversation ordering (unique with `conversation_id`) |
| `is_active` | `false` when superseded by edit/regenerate |
| `grounded` | `true` / `false` / `null` (general chat without retrieval) |
| `model`, `provider`, token fields, `latency_ms`, `finish_reason`, `error_code` | Usage metadata (tokens may be **null** if the provider omits them) |
| `client_request_id` | Optional idempotency key (unique per user + conversation when set) |
| `regenerated_from_message_id`, `edited_from_message_id` | Lineage for regenerate/edit |
| `metadata` | JSONB (ORM: `message_metadata`) |

### `MessageCitation`

Historical snapshot of RAG citations on an assistant message (survives if source chunks/documents are later deleted — FKs `SET NULL` where applicable).

| Field | Purpose |
| --- | --- |
| `message_id`, `conversation_id`, `user_id` | Scoped ownership |
| `citation_index`, `citation_id` | Stable index; API exposes `citation_id` like `"[1]"` |
| `document_id`, `chunk_id`, `filename`, `page_number`, `chunk_index`, `excerpt`, `similarity_score` | Citation card payload |

---

## Ownership

- Every conversation and message row is tied to **`user_id`**. List, detail, message send, edit, regenerate, archive, and delete require the authenticated active user to own the row.
- Cross-user access returns **`404`** (`conversation_not_found` / `message_not_found`) — no existence leak.
- RAG retrieval inside chat uses the same document ownership rules as Phase 4.
- Hard **`DELETE /conversations/{id}`** removes the conversation and all messages/citations (CASCADE). **Not restorable.**

---

## API surface

Base URL in examples: **`http://localhost:18000`** (this workspace’s published backend port). Prefix: **`/api/v1`**. All conversation routes require **`Authorization: Bearer <access_token>`** unless noted.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/conversations` | Create (optional `title`, `document_ids`, `initial_message`) |
| `GET` | `/conversations` | List (`limit`, `offset`, `include_archived`, `status`, `q`) |
| `GET` | `/conversations/{id}` | Detail + active messages (newest page, ascending in response) |
| `PATCH` | `/conversations/{id}` | Rename (`title`; sets `title_is_auto=false`) |
| `POST` | `/conversations/{id}/archive` | Archive |
| `POST` | `/conversations/{id}/unarchive` | Restore to active |
| `DELETE` | `/conversations/{id}` | Hard delete (`204`) |
| `POST` | `/conversations/{id}/messages` | Send message (non-streaming) |
| `POST` | `/conversations/{id}/messages/stream` | Send message (SSE) |
| `PATCH` | `/conversations/{id}/messages/{message_id}` | Edit **latest active user** message only |
| `POST` | `/conversations/{id}/regenerate` | Regenerate **latest active assistant** reply |
| `GET` | `/usage/summary` | Per-user usage aggregates |

### Curl examples

```bash
BASE="http://localhost:18000"
COOKIE_JAR="$(mktemp)"

# Register and capture access token (see AUTHENTICATION.md for login/refresh)
curl -fsS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -X POST "$BASE/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"chat-demo@example.com","password":"StrongDemoPassword123!","full_name":"Chat Demo"}' \
  | tee /tmp/cortexa-auth.json

ACCESS="$(python3 -c 'import json; print(json.load(open("/tmp/cortexa-auth.json"))["access_token"])')"

# Create conversation with first message (RAG over all ready docs when document_ids omitted)
curl -fsS -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/conversations" \
  -d '{"initial_message":"Summarize my uploaded documents in one sentence."}' \
  | python3 -m json.tool

CONV_ID="<conversation-uuid-from-response>"

# Non-streaming follow-up
curl -fsS -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/conversations/$CONV_ID/messages" \
  -d '{"content":"What formats can I upload?"}' \
  | python3 -m json.tool

# Streaming (SSE)
curl -N -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -X POST "$BASE/api/v1/conversations/$CONV_ID/messages/stream" \
  -d '{"content":"List key platform features."}'

# General chat (no retrieval) — requires CHAT_GENERAL_MODE_ENABLED=true
curl -fsS -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/conversations/$CONV_ID/messages" \
  -d '{"content":"Hello","document_ids":[]}' \
  | python3 -m json.tool

# Regenerate latest assistant answer
curl -fsS -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/conversations/$CONV_ID/regenerate" \
  -d '{}' \
  | python3 -m json.tool

# Usage summary
curl -fsS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/v1/usage/summary" | python3 -m json.tool

rm -f "$COOKIE_JAR" /tmp/cortexa-auth.json
```

---

## SSE event schema (conversation stream)

Media type: `text/event-stream`. Events match the normalized LLM stream plus conversation-specific payloads.

| Event | Data (JSON) |
| --- | --- |
| `start` | `conversation_id`, `user_message_id`, `assistant_message_id` |
| `delta` | `{ "content": "<token chunk>" }` |
| `citation` | `{ "citation": { ... } }` — emitted before LLM tokens when RAG chunks exist |
| `metadata` | `model`, `provider`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms` |
| `complete` | `{ "message": <MessageResponse JSON> }` |
| `error` | `{ "error": { "code", "message" } }` |

Idempotent replays (same `client_request_id`) stream stored assistant content via the same event sequence.

---

## Context window priority

Implemented in `app/conversations/context.py`:

1. **Current user message** (always included)
2. **Retrieved RAG context** (bounded by `RAG_MAX_CONTEXT_CHARACTERS`)
3. **Recent conversation history** (active, complete user/assistant turns)
4. **Conversation summary** (only when history was trimmed)
5. **Trim oldest** history first when over `CONVERSATION_MAX_HISTORY_MESSAGES`, `CONVERSATION_MAX_HISTORY_CHARACTERS`, or `CONVERSATION_MAX_CONTEXT_CHARACTERS`

---

## Rolling summary

- Controlled by `CONVERSATION_SUMMARY_ENABLED` and `CONVERSATION_SUMMARY_TRIGGER_MESSAGES` (default **12** active complete user+assistant messages).
- When active message count exceeds the trigger and history length exceeds `CONVERSATION_MAX_HISTORY_MESSAGES`, older turns are summarized into `Conversation.summary` (scoped to **this conversation only**).
- Summary generation runs **after** a successful assistant finalize; **failures are logged and do not fail the chat request**.
- Tests inject a **fake summarizer** (see `backend/tests/conftest.py`) to avoid live LLM calls.

---

## Title generation

- After the **first completed assistant** reply, if `CONVERSATION_AUTO_TITLE_ENABLED`, `title_is_auto` is still true, and the title is still the default `"New conversation"`, the service generates a short title from the first user/assistant pair.
- **User rename** (`PATCH`) sets `title_is_auto=false` and preserves the chosen title.
- Title generation failure does not fail the chat turn.

---

## Document scope (`document_ids`)

| Request value | Behavior |
| --- | --- |
| **Omitted** (`null`) | Retrieve from **all owned documents** in `ready` state |
| **`[]`** | **No retrieval** — general LLM chat when `CHAT_GENERAL_MODE_ENABLED=true`; otherwise rejected |
| **Non-empty UUID list** | Retrieve only from those documents (must be owned + ready) |

The standalone `POST /api/v1/rag/query` endpoint from Phase 4 remains available for one-shot Q&A without persisting a conversation.

---

## No-context policy

When retrieval is attempted (scope is not general chat) and **no chunks** pass the similarity threshold:

- Assistant content is a fixed fallback: *"I could not find enough information in your uploaded documents to answer that question."*
- `grounded=false`, `citations=[]`, `finish_reason=no_context`
- **No LLM call** (same policy as Phase 4 RAG query)

---

## Edit (latest user message)

- `PATCH /conversations/{id}/messages/{message_id}` with new `content`.
- Only the **latest active user** message may be edited.
- Sets `edited_from_message_id` on the replacement user row; prior user row and **all following active messages** are marked `is_active=false`.
- **Does not** auto-generate a new assistant reply — send a message or call regenerate explicitly.

---

## Regenerate (latest assistant)

- `POST /conversations/{id}/regenerate` with optional `document_ids`, `top_k`, `temperature`, `max_tokens`, `client_request_id`.
- Supersedes the latest active assistant after the latest user message (`is_active=false`).
- New assistant row links `regenerated_from_message_id` to the previous assistant.
- **Does not** duplicate the user message.

---

## Idempotency (`client_request_id`)

Optional UUID on `CreateMessageRequest` and `RegenerateRequest`. Unique per `(user_id, conversation_id, client_request_id)`.

- **Send message:** if the user message already exists, returns the existing user + following assistant pair (non-stream) or replays SSE (stream).
- If the user row exists but no assistant yet, returns **`409`** (`duplicate_client_request`).

---

## Archive and delete

- **Archived** conversations reject new messages, stream, edit, and regenerate until **unarchive**.
- Archive/unarchive do not delete messages.
- **Delete** is permanent (conversation + messages + citations).

---

## Usage

`GET /api/v1/usage/summary` returns counts (conversations, messages, documents) and sums of **known** token fields across the user’s messages. Null provider token counts are excluded from sums.

---

## Migrations & readiness

- Alembic revision: `0004_phase5_conversations` (tables `conversations`, `messages`, `message_citations`; enums `conversation_status`, `message_role`, `message_status`).
- Backend Docker entrypoint runs `alembic upgrade head` **before** Uvicorn so the connection pool never starts against a missing schema.
- Migration failure aborts container startup.
- `/ready` (and `/health/ready`) returns **503** when migrations are behind head or conversation tables are missing.
- After applying migrations to a running backend, **restart the backend** (stale asyncpg type/statement caches).

---

## Frontend

- Routes: `/chat` (new/list), `/chat/[conversationId]` (thread).
- Client: `frontend/services/conversations.ts` — authenticated fetch + SSE via `ReadableStream` (Authorization header).
- Open **`http://localhost:13000/chat`** when the stack is up.

---

## Configuration

See `.env.example` for `CONVERSATION_*`, `CHAT_*`, and related RAG limits.

---

## Known limitations

- **No cross-conversation memory** — each thread is isolated; summary does not span conversations.
- **No user profile / long-term memory** store.
- **Token usage fields may be null** depending on Ollama response metadata.
- **Deleted conversations are not restorable.**
- Edit does not chain into automatic regeneration.
- No org/tenant shared conversations.
- Agent tools are covered in Phase 6 ([AGENT_TOOLS.md](AGENT_TOOLS.md)).
- Long-term memory is covered in Phase 7 ([LONG_TERM_MEMORY.md](LONG_TERM_MEMORY.md)).
