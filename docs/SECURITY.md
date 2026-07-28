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

## Phase 2 Security Posture

Implemented on top of Phase 1:

- Request size and output token limits for LLM APIs
- Restricted message roles (`system` / `user` / `assistant`)
- Structured LLM errors without upstream body leakage
- Prompt/completion bodies are not logged by default
- Shared outbound httpx client with explicit timeouts (no indefinite retries)
- `/ready` remains independent of Ollama availability

Still deferred:

- Authentication / session security
- Rate limiting enforcement
- Tool permission model
- Prompt-injection mitigations beyond input size limits

---

## Prompt Injection / Tools / Memory

Documented for later phases. Phase 2 enforces input size/role limits only.

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
