# Security

Cortexa AI Agent Platform — security philosophy and controls.

Cortexa is **local-first**. Security prioritizes preventing accidental data exfiltration, unsafe tool execution, and secret leakage while remaining practical for single-operator and small-team local deployments.

---

## Local-First Execution

- Default inference, embeddings, and speech will run on local runtimes in later phases.
- Phase 1 does not contact cloud AI APIs and does not download models automatically.
- Phase 2 integrates Ollama locally only. Models are never auto-pulled.

---

## No Hidden Cloud APIs

- Application code must not embed undeclared SaaS AI calls.
- Dependencies should prefer libraries that do not phone home by default.
- Next.js telemetry is disabled in the frontend container (`NEXT_TELEMETRY_DISABLED=1`).

---

## Secret Management

| Practice | Requirement |
| --- | --- |
| Repository | No live secrets; `.env` is gitignored |
| Templates | `.env.example` contains non-production placeholders only |
| Runtime | Secrets via environment |
| Logs | Do not log passwords, `Authorization`, cookies, or DB/Redis URLs |
| Errors | Client responses must not include stack traces or internal exception strings |

Phase 1 local credentials:

- `POSTGRES_PASSWORD=local_development_only` (template only — change for any shared host)

---

## Phase 5 Security Posture

Implemented on top of Phase 4:

- Conversation and message APIs require an authenticated active user
- Conversations, messages, and message citations are scoped by **`user_id`**; cross-user IDs return `404`
- Archived conversations reject new messages until unarchived
- Hard delete removes conversation data permanently (CASCADE)
- Chat retrieval reuses Phase 4 document ownership isolation
- Optional `client_request_id` idempotency reduces duplicate sends on retries (per user + conversation)

Still deferred:

- Production rate-limit enforcement on conversation send/stream endpoints
- Cross-conversation memory and shared org threads

---

## Phase 4 Security Posture

Implemented on top of Phase 1–3:

- Argon2id password hashing; passwords never logged or returned
- Password reset tokens stored as SHA-256 hashes only; single-use; expiring; refresh sessions revoked on reset
- Forgot-password responses are enumeration-safe (same message for known/unknown emails)
- Short-lived JWT access tokens (`type=access`, explicit algorithm allow-list)
- Opaque refresh tokens stored only as SHA-256 hashes
- Refresh rotation + family revocation on reuse
- HttpOnly refresh cookies; access tokens stay in browser memory
- Disabled accounts rejected for login, refresh, and bearer access
- LLM generate/stream and document/RAG APIs require an authenticated active user
- Document ownership isolation (list/detail/delete/retrieval scoped by `user_id`)
- Upload validation: extension allow-list, size cap, content sniffing, path-safe storage keys
- Local storage rejects path traversal and uses atomic writes
- Duplicate rejection by per-user content checksum
- CORS credentials limited to explicit approved origins
- Structured errors without SQL/crypto/path leakage

Still deferred:

- Production rate-limit enforcement (login/register/refresh/upload must be limited in production)
- Email verification / production password-reset SMTP delivery
- Social login / OAuth providers
- Admin tooling and org/tenant isolation
- Tool permission model
- Advanced prompt-injection mitigations beyond grounded prompts + size limits

---

## Prompt Injection / Tools / Memory

Documented for later phases. Phase 4–5 use grounded system prompts and retrieval scoping; Phase 2–3 also enforce input size/role limits. Conversation summaries and titles are generated via the same local LLM with bounded prompts.

---

## Threat Model Snapshot (Local Deploy)

| Threat | Mitigation direction |
| --- | --- |
| Secret committed to git | `.gitignore`, reviews, `make secrets-check` |
| Credential leakage in logs/errors | Structured logging + sanitized readiness/errors |
| DB/Redis exposed broadly | Localhost bind + Docker network |
| Accidental model downloads | No auto-pull on build/startup; explicit `ollama pull` only |
| Prompt/completion leakage | LLM logs omit message bodies by default |
| Supply chain | Pinned Compose image tags where practical |

---

## Containers

- Backend runs as UID 10001 (`cortexa`)
- Frontend runs as UID 10001 (`cortexa`)
- Healthchecks use localhost inside containers
