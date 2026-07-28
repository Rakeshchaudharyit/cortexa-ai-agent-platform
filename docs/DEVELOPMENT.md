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
| `app/api/` | Routers, HTTP mapping to services |
| `app/core/` | Settings, logging, exceptions, lifespan |
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
| `make up` / `make down` | Start / stop Compose |
| `make test` | Backend + frontend tests |
| `make lint` / `make typecheck` | Quality gates |
| `make health` / `make ready` | Probe API |
| `make migrate` | Alembic upgrade head (Docker) |
| `make validate` | Full Phase 1 + Phase 2 validation suite |

Commands fail when underlying checks fail.

---

## Environment Variables

See `.env.example`. Key variables:

- `APP_*`, `API_PREFIX`, `LOG_LEVEL`, `BACKEND_*`
- `POSTGRES_*`, `DATABASE_URL`
- `REDIS_*`, `REDIS_URL`
- `CORS_ALLOWED_ORIGINS`
- `NEXT_PUBLIC_API_BASE_URL`
- Phase 2 LLM: `LLM_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`,
  `OLLAMA_REQUEST_TIMEOUT_SECONDS`, `OLLAMA_CONNECT_TIMEOUT_SECONDS`,
  `LLM_MAX_INPUT_CHARACTERS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_DEFAULT_TEMPERATURE`

Security placeholders may exist but are not implemented yet.

---

## Health / Readiness / LLM Status

- `/health` — process alive; no DB/Redis/Ollama
- `/ready` — Postgres `SELECT 1` and Redis `PING`; independent results; `503` if any fail
- `/api/v1/llm/status` — Ollama reachability + configured model availability; **does not** gate `/ready`
- Errors never include credentials, URLs with secrets, or stack traces

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
| `/ready` → 503 database error | Postgres not healthy / wrong URL | `docker compose ps`, check `DATABASE_URL` |
| `/ready` → 503 redis error | Redis stopped | `docker compose start redis` |
| Frontend shows backend unavailable | API not up or wrong `NEXT_PUBLIC_API_BASE_URL` | Confirm health curl on the published backend port |
| Frontend `/_next/static` 404 or icon 500 | `.next` polluted by root-owned build | Restart frontend; validate runs as `-u cortexa` then restarts |
| LLM status `provider_unavailable` | Ollama down / wrong base URL | `docker compose ps ollama`; use `http://ollama:11434` |
| LLM status `model_unavailable` | Model not pulled | `docker compose exec ollama ollama pull qwen2.5:7b` |
| Generate → 504 | Provider timeout | Raise `OLLAMA_REQUEST_TIMEOUT_SECONDS` or reduce `max_tokens` |
| Generate → 424 | Model missing | Pull model manually |
| Docker bind mount denied | Docker Desktop file sharing | Move repo under an allowed path (for example `~/Projects`) |

---

## Current Limitations (Phase 2)

- No authentication
- No chat product UI / conversation history
- No RAG, memory, tools, or voice
- No domain database tables beyond Alembic baseline
- Models must be pulled manually
- Frontend remains an operator status surface, not an enterprise dashboard

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
