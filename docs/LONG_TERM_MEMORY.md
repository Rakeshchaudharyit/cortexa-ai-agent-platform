# Long-Term Memory (Phase 7)

## Purpose

Cortexa Phase 7 adds a **user-controlled** long-term memory layer so the assistant can retain approved preferences, project context, and durable instructions across conversations.

This is intentionally **not** hidden profiling. Users can view, edit, confirm, archive, and delete memories at any time.

## Distinction from other context

| Concept | Scope | Persistence |
|---------|-------|-------------|
| Conversation history | One conversation | Messages table |
| Conversation summary | One conversation | Conversation.summary |
| Document knowledge (RAG) | User-owned uploads | document_chunks + embeddings |
| Long-term memory | Cross-conversation, user-owned | user_memories (+ optional embeddings) |

These are never mixed in the same table or treated as interchangeable in prompts.

## Architecture

```
User message
  → auth + ownership
  → detect explicit memory intent (remember/forget/list/update/disable)
  → retrieve relevant active memories (bounded)
  → build context (system + memory block + history + RAG)
  → agent / LLM loop
  → optional conservative extraction after completed turn
  → audit + stream lifecycle events
```

Package: `backend/app/memory/`

- `service.py` — CRUD, settings, conflicts, ownership
- `sanitizer.py` — deterministic secret rejection
- `extractor.py` — conservative candidate extraction
- `retrieval.py` — ranking + limits
- `intent.py` — deterministic command parsing
- `chat_integration.py` — chat orchestration helpers
- `repository.py` — persistence

## Models

### UserMemory

Durable memory owned by `user_id`, with category, status, source, confidence, importance, expiration, soft-delete, optional embedding (768-d pgvector), and version.

### UserMemorySettings

Per-user controls. Defaults:

- `memory_enabled=true`
- `automatic_extraction_enabled=false` (never silently enabled for existing users)
- `suggestions_enabled=true`
- `require_confirmation=true`
- `include_memories_in_chat=true`
- `maximum_active_memories` capped by env

### MemoryAuditEvent

Append-only audit trail. Metadata is safe/bounded — never raw secrets or full sensitive content.

### Conversation overrides

- `memory_enabled_override` (nullable)
- `memory_context_used`
- `memory_disabled_reason`

## Categories

`preference`, `personal_context`, `project`, `instruction`, `workflow`, `technical_context`, `decision`, `goal`, `relationship_context`, `other`

Avoid highly sensitive identity categories.

## Statuses

`proposed` → `active` → `archived` / `rejected` / `deleted`

## Sources

`explicit_user_request`, `assistant_suggestion`, `automatic_extraction`, `imported`, `system_generated`

## Explicit remember / forget

Deterministic intent parsing handles phrases such as:

- “Remember that I prefer Python examples.”
- “Forget my frontend language preference.”
- “What do you remember about this project?”
- “Do not use memory in this conversation.”

Explicit remember validates/sanitizes content, applies confirmation policy, audits, and acknowledges in chat.

Forget matches owned active memories. Ambiguous matches ask for clarification instead of deleting multiple.

## Extraction

Automatic extraction is **off by default**. Suggestions may still propose candidates that require confirmation.

Never auto-save:

- secrets / tokens / passwords
- transient questions
- assistant speculation
- full document passages
- chain-of-thought

## Deduplication and conflicts

1. Normalize content
2. Exact duplicate check
3. Optional embedding similarity
4. Preference/instruction conflicts: new explicit preference supersedes/archives the old one with audit

## Retrieval and injection

Only **active**, non-expired, owned memories are retrieved. Ranking blends semantic similarity (when available), keyword overlap, importance, and light recency/frequency.

Strict limits:

- `MEMORY_MAX_RETRIEVAL_RESULTS`
- `MEMORY_CONTEXT_MAX_CHARACTERS`
- `MEMORY_MIN_RELEVANCE_SCORE`

Memory context is appended to the system prompt as a clearly labeled block, separate from RAG context.

## Tools

Read-only tools:

- `memory_list`
- `memory_search`

Write actions go through MemoryService and explicit user intent — the model cannot silently create personal memories.

## APIs

Authenticated:

- `GET/POST /api/v1/memories`
- `GET/PATCH/DELETE /api/v1/memories/{id}`
- `POST .../confirm|archive|restore|reject`
- `GET/PATCH /api/v1/memory-settings`
- `GET /api/v1/memory-audit`
- `PATCH /api/v1/conversations/{id}/memory`

No embeddings are returned. Cross-user access returns a safe 404.

## Streaming events

- `memory_retrieval_started`
- `memory_retrieval_completed`
- `memory_candidate_proposed`
- `memory_saved`
- `memory_updated`
- `memory_archived`
- `memory_deleted`
- `memory_action_failed`

## Frontend

- `/memories` — list, filter, search, confirm/reject/archive/restore/delete, settings
- Chat — memory activity indicator, per-conversation toggle, proposal card
- Dashboard — Phase 7 milestone + Long-Term Memory capability card

## Deletion behavior

Soft-delete:

- status=`deleted`
- content/title redacted to placeholders
- embedding cleared
- excluded from retrieval and active listings
- audit records remain without sensitive payload

## Security and privacy

- Strict user ownership on every query
- Deterministic sensitive-pattern rejection (not LLM-only)
- Bounded content / active count / retrieval
- No hidden profiling
- No cross-user memory
- No organization-wide shared memory in Phase 7

## Adding a category

1. Add value to `MemoryCategory` enum
2. Extend Alembic enum in a new migration (do not edit 0008 in place after deploy)
3. Update docs + frontend filter list
4. Add tests

## Test strategy

Backend: migration, sanitizer, ownership, lifecycle, retrieval, intent, API auth, conflict supersede, settings defaults.

Frontend: `/memories` auth + actions + settings; chat memory activity; Phase 7 dashboard.

Tests run only against `cortexa_agent_test`.

## Known limitations

- Pattern-based secret detection is conservative but not perfect
- Semantic duplicate detection depends on embedding availability
- Extraction heuristics prefer clear preference/project statements
- No shared/org memory, no biometric/health profiles

## Phase 8 exclusions

Not in Phase 7: Gmail, Calendar, Slack, Teams, remote MCP, unrestricted browsing, shell/SQL/Python execution, scheduled autonomous agents, STT/TTS, mobile apps.
