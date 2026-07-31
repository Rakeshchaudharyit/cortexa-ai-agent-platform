# Development Standards

Coding and engineering standards for Cortexa AI Agent Platform.

---

## Core Principles

1. **Clean Architecture** — keep framework and IO at the edges.
2. **SOLID** — prefer small modules with clear responsibilities.
3. **Explicit over clever** — readable control flow beats abstraction theater.
4. **Honesty** — never ship fake business logic that pretends a feature works.
5. **Phase discipline** — do not implement future phases early.

---

## Local Setup

```bash
cp .env.example .env
docker compose up -d --build
```

Native (optional):

```bash
make install
# Ensure Postgres/Redis match .env (Compose ports bind to 127.0.0.1 by default)
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

---

## Backend (Python 3.12 / FastAPI)

### Structure

| Package | Allowed contents |
| --- | --- |
| `app/api/` | Routers, HTTP mapping to services, auth deps |
| `app/core/` | Settings, logging, exceptions, lifespan |
| `app/models/` | SQLAlchemy ORM models |
| `app/security/` | Password hashing and token helpers |
| `app/schemas/` | Pydantic DTOs |
| `app/services/` | Business / orchestration logic |
| `app/providers/` | External system adapters |
| `app/db/` | Engine, sessions, DB health |
| `tests/` | Unit / API tests |

### Rules

- Routes call **services** only (not DB engines, Redis clients, or Ollama HTTP).
- Services call providers / `db` helpers / `LLMProvider` for infrastructure and models.
- Ollama transport details stay inside `app/llm/providers/ollama.py`.
- Use type hints; prefer Pydantic models at boundaries.
- Do not log full prompts or generated content by default.

### Style & tooling

- Format / lint: Ruff
- Types: mypy (`strict`)
- Tests: pytest + pytest-asyncio + HTTPX

```bash
cd backend
ruff check .
ruff format --check .
mypy app
pytest
```

---

## Frontend (Node.js 22 / Next.js / TypeScript)

### Structure

| Directory | Allowed contents |
| --- | --- |
| `app/` | Routes, layouts, pages |
| `components/` | Presentational / status UI |
| `services/` | Backend API helpers |
| `lib/` | API client + config |
| `types/` | Shared TS types |
| `tests/` | Vitest tests |

### Rules

- TypeScript **strict** mode.
- Browser talks to Cortexa backend only — never to Ollama.
- Phase 1 uses **client-side fetching** for health/readiness/system info (see `frontend/README.md`).
- No fabricated dashboard metrics.

### Style & tooling

```bash
cd frontend
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

---

## Makefile Commands

| Command | Purpose |
| --- | --- |
| `make up` / `make down` | Start / stop Compose (`down` preserves volumes) |
| `make compose-identity` | Verify Compose project name, Postgres volume, DB name |
| `make reset-dev-database` | Destructive reset only (typed confirmation + backup) |
| `make test` | Backend + frontend tests |
| `make test-services-up` / `test-db-migrate` / `test-backend` | Isolated test Postgres/Redis (`cortexa_agent_test`) |
| `make lint` / `make typecheck` | Quality gates |
| `make health` / `make ready` | Probe API |
| `make migrate` | Alembic upgrade head (Docker) |
| `make validate` | Full Phase 1–5.1 validation suite (includes compose identity) |

Commands fail when underlying checks fail.

**Backend tests** run only against the isolated Compose project `cortexa-test`
(`docker-compose.test.yml`): database `cortexa_agent_test`, identity
`cortexa-agent-test`, volume `cortexa_postgres_test_data`. They never use
`cortexa_agent` / `cortexa_postgres_data`. Use `make test-backend` or
`make validate` — never `docker compose exec backend pytest`.

---

## Environment Variables

See `.env.example`. Key variables:

- `APP_*`, `API_PREFIX`, `LOG_LEVEL`, `BACKEND_*`
- `POSTGRES_*`, `DATABASE_URL`, `EXPECTED_APPLICATION_ID`, `EXPECTED_DATABASE_IDENTITY`
- `REDIS_*`, `REDIS_URL`
- `CORS_ALLOWED_ORIGINS`, `FRONTEND_ORIGIN`
- `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_PASSWORD_RESET_DEV_NOTICE`

**Auth hostname rule:** never mix `localhost` and `127.0.0.1` between the browser URL and `NEXT_PUBLIC_API_BASE_URL`. Refresh cookies are host-bound (`SameSite=Lax`); a mismatch makes login succeed then lose the session on reload. Prefer `http://127.0.0.1:13000` + `http://127.0.0.1:18000` for this workspace’s published ports. Run `./scripts/check_auth_hostname.sh`.

- Phase 2 LLM: `LLM_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`,
  `OLLAMA_REQUEST_TIMEOUT_SECONDS`, `OLLAMA_CONNECT_TIMEOUT_SECONDS`,
  `LLM_MAX_INPUT_CHARACTERS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_DEFAULT_TEMPERATURE`
- Phase 5 conversations: `CONVERSATION_*`, `CHAT_GENERAL_MODE_ENABLED`, `CHAT_DEFAULT_*`, `MESSAGE_MAX_RESPONSE_TOKENS` (see `.env.example`)
- Phase 6 agent tools: `AGENT_TOOLS_ENABLED`, `AGENT_MAX_TOOL_ITERATIONS`, `AGENT_TOOL_TIMEOUT_SECONDS`, `AGENT_MAX_RESULT_BYTES` (see `.env.example` and `docs/AGENT_TOOLS.md`)

Security placeholders may exist but are not implemented yet.

---

## Health / Readiness / LLM Status

- `/health` and `/health/live` — process alive; no DB/Redis/Ollama
- `/ready` and `/health/ready` — Postgres connectivity, Alembic at head, required Phase 5 conversation tables, database identity metadata, and Redis `PING`; independent results; `503` if any fail
- `/api/v1/llm/status` — Ollama reachability + configured model availability; **does not** gate `/ready`
- Errors never include credentials, URLs with secrets, or stack traces

### Migrations and connection pools

- The backend Docker entrypoint runs `alembic upgrade head` **before** Uvicorn starts, so the application connection pool is created against the post-migration schema.
- Migration failure aborts container startup (`set -e`); the API must not serve a missing schema.
- Applying migrations to a **running** backend requires a **backend restart**. Long-lived asyncpg connections can retain stale type OIDs / prepared statements after DDL (symptoms: `cache lookup failed for type`, missing relations).

### Frontend `.next` cache

- Never delete selected files under `.next/cache` while Next.js is running (causes webpack `ENOENT` on `.pack.gz`).
- Prefer: stop the frontend → delete the entire `.next` tree → restart/rebuild cleanly.
- `scripts/check_frontend_cache_safety.sh` guards validate/startup scripts against partial live deletes.

---

## Phase 2 — Local LLM (Ollama)

### Start stack

```bash
cp .env.example .env
docker compose up -d --build
```

### Pull the model manually (required for generation)

Models are **not** pulled on image build or normal startup:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama list
```

### Check status

```bash
curl -i http://localhost:18000/api/v1/llm/status
# With default .env.example ports use :8000
```

Expected when Ollama is up but the model is missing:

- `provider_reachable: true`
- `model_available: false`
- `status: model_unavailable`

### Non-streaming generation

```bash
curl -sS http://localhost:18000/api/v1/llm/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
    "temperature": 0.2,
    "max_tokens": 64
  }'
```

### Streaming (SSE)

```bash
curl -N http://localhost:18000/api/v1/llm/stream \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{
    "messages": [{"role": "user", "content": "Count from 1 to 3."}],
    "max_tokens": 64
  }'
```

SSE events: `start`, `delta`, `complete`, `error`.

### Request validation

- Roles: `system`, `user`, `assistant` only
- Temperature: `0.0`–`2.0`
- At least one message; content cannot be blank
- Total input characters capped by `LLM_MAX_INPUT_CHARACTERS`
- `max_tokens` capped by `LLM_MAX_OUTPUT_TOKENS`

### Host vs container Ollama URLs

| Caller | URL |
| --- | --- |
| Backend container → Ollama | `http://ollama:11434` (`OLLAMA_BASE_URL`) |
| Host tooling → Ollama | `http://127.0.0.1:11435` |

Never set `OLLAMA_BASE_URL=http://localhost:11435` inside the backend container.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `/ready` → 503 database error | Postgres not healthy / wrong URL / migrations behind / missing tables | `docker compose ps`, `alembic current`, check `DATABASE_URL`; restart backend after migrate |
| `/ready` → 503 redis error | Redis stopped | `docker compose start redis` |
| `relation "conversations" does not exist` | Migration 0004 not applied / entrypoint skipped | Rebuild backend; confirm entrypoint runs `alembic upgrade head`; restart |
| `cache lookup failed for type` | Stale asyncpg cache after DDL on a live process | Restart backend after migrations |
| Frontend shows backend unavailable | API not up, not ready, or wrong `NEXT_PUBLIC_API_BASE_URL` | Confirm `/health/live` + `/health/ready` on the published backend port |
| Frontend `/_next/static` 404, icon 500, or `.pack.gz` ENOENT | `.next` cleared while Next was running, or polluted cache | Stop frontend; delete entire `.next`; restart (never partial live deletes) |
| LLM status `provider_unavailable` | Ollama down / wrong base URL | `docker compose ps ollama`; use `http://ollama:11434` |
| LLM status `model_unavailable` | Model not pulled | `docker compose exec ollama ollama pull qwen2.5:7b` |
| Embedding status `model_unavailable` | Embedding model not pulled | `docker compose exec ollama ollama pull nomic-embed-text` |
| Document upload `415` | Unsupported type | Use `.txt`, `.md`, `.pdf`, or `.docx` |
| Document upload `409` | Duplicate checksum | File already uploaded for this user |
| RAG returns no citations | No ready docs / low similarity | Upload a document; lower `RAG_MIN_SIMILARITY` only in tests |
| Chat no-context fallback | Scoped retrieval returned no chunks | Expected — fixed message, no LLM; upload relevant docs or widen scope |
| Archived conversation rejects send | By design | `POST .../unarchive` before messaging |
| Generate → 504 | Provider timeout | Raise `OLLAMA_REQUEST_TIMEOUT_SECONDS` or reduce `max_tokens` |
| Generate → 424 | Model missing | Pull model manually |
| Invalid email or password after register | Typo at registration (no confirmation before Phase 5.1); password whitespace mismatch; wrong API host | Use Show password + confirm field; passwords are not trimmed; see AUTHENTICATION.md troubleshooting |
| Need a local password-reset link | Development delivery does not send email; link is in Redis | Request forgot-password, then `docker compose exec backend python -m app.cli.get_password_reset_link --email …` |

---

## Phase 5 — Conversations & chat

### Manual smoke

After auth and at least one **ready** document (optional for general chat with `document_ids: []`):

```bash
BASE="http://localhost:18000"
# Obtain ACCESS as in AUTHENTICATION.md or RAG.md

curl -fsS -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/conversations" \
  -d '{"initial_message":"Hello"}' | python3 -m json.tool
```

Open **`http://localhost:13000/chat`** for the product UI (sidebar, streaming, citations).

### Tests

```bash
cd backend && pytest tests/test_conversations_api.py
cd frontend && npm test -- --run tests/chat.test.tsx
```

Backend tests use injected **fake title/summarizer** callables and mocked LLM where appropriate — no live Ollama required for the conversation API suite.

Full details: [CONVERSATIONS.md](CONVERSATIONS.md).

---

## Current Limitations (Phase 6)

- No cross-conversation or profile memory (only per-conversation rolling summary)
- Native Ollama tool calling depends on the installed model — do not assume it works without verification
- No external SaaS tools, web browsing, shell, MCP, or voice
- Document ingest remains synchronous (request-scoped); no background workers
- PDF text extraction only (no OCR); encrypted PDFs rejected
- Models must be pulled manually (`qwen2.5:7b`, `nomic-embed-text`)
- Deleted conversations are not restorable; token fields may be null from the provider
- Home page is the Phase 6 platform overview (capabilities, quick actions, system status) plus documents; `/chat` is the conversation product surface; `/tools` shows owned tool execution history

---

## Git & Commits

- Do not commit secrets or local `.env` files.
- Automation must not create commits unless explicitly requested.

---

## What Not To Do

- Do not put infrastructure logic in routers.
- Do not create fake agent success endpoints.
- Do not auto-pull large models during image build or startup.
- Do not add cloud AI SDKs without a phase requirement.
- Do not weaken typing to ship faster.
- Do not log full prompts or completions by default.
