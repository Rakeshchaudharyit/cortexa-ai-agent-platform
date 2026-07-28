# Roadmap

Cortexa AI Agent Platform — phased delivery plan.

Rules:

- Phases are sequential and audited.
- Do not implement future phases early.
- Do not ship placeholder business logic that pretends a feature exists.
- Each phase must pass local validation before the next phase starts.

---

## Phase 0 — Architecture & Engineering Foundation

**Status:** Complete (`v0.1.0-phase0`)

---

## Phase 1 — Application Foundation

**Status:** Complete

### Objective

Convert the Phase 0 scaffold into a real, locally runnable application foundation.

### Deliverables

- FastAPI app with settings, logging, CORS, correlation IDs, JSON errors
- `GET /health`, `GET /ready`, `GET /api/v1/system/info`
- SQLAlchemy async + Alembic baseline (no domain tables)
- Async Redis provider
- Next.js App Router system-status page with typed API client
- Dockerfiles + Compose with healthchecks
- Pytest / Vitest / Ruff / mypy / ESLint / TypeScript / Next build

### Exclusions

- Ollama integration, LLM calls, chat UI
- Auth, users, orgs, RAG, embeddings, memory, tools, voice

---

## Phase 2 — Local LLM Provider and Ollama Integration

**Status:** Current

### Objective

Establish a production-quality, provider-neutral LLM layer with Ollama as the first provider.

### Deliverables

- `LLMProvider` protocol and Ollama implementation
- Typed settings for provider/model/timeouts/limits
- Non-streaming and streaming (SSE) generation APIs
- Dedicated LLM status endpoint (does not gate `/ready`)
- Deterministic tests with mocked HTTP / fake providers
- Minimal frontend LLM status display (no chat product)

### Acceptance Criteria

1. Phase 1 Docker and frontend asset validation still passes
2. Provider abstraction is implemented
3. Ollama provider is implemented without auto-pulling models
4. `GET /api/v1/llm/status` works with controlled missing-model behavior
5. `POST /api/v1/llm/generate` and `POST /api/v1/llm/stream` work
6. Errors use the safe normalized envelope
7. Tests do not require a downloaded model
8. Backend pytest / ruff / mypy pass
9. Frontend lint / typecheck / test / build pass
10. Documentation covers provider usage and troubleshooting

### Exclusions

- Authentication
- RAG / embeddings
- Persistent memory
- Agent tools
- Voice
- Production chat UI / conversation history

---

## Phase 3 — Frontend Application Expansion

### Objective

Expand the status UI toward a durable application shell without fabricating dashboard metrics.

### Exclusions

- Full enterprise analytics dashboard
- Direct browser calls to Ollama

---

## Phase 4 — Database Models, Migrations & Repositories

### Objective

Introduce domain persistence with migrations, SQLAlchemy models, and repository interfaces.

---

## Phase 5 — Chat / Agent Core Services

### Objective

Deliver conversational and agent orchestration with streaming and persisted turns.

---

## Phase 6 — Embeddings, Vector Store & RAG

### Objective

Local embeddings, vector store provider, ingestion, and retrieval-augmented generation.

---

## Phase 7 — Memory System

### Objective

Short-term and long-term memory with privacy controls and retention policies.

---

## Phase 8 — Tool Calling Framework

### Objective

Structured tool registration, permission gating, and audited execution.

---

## Phase 9 — Speech (STT / TTS)

### Objective

Local speech-to-text and text-to-speech providers.

---

## Phase 10 — Enterprise Dashboard & Analytics

### Objective

Operator dashboard with real metrics derived from local telemetry.

---

## Phase 11 — Hardening, Observability & Security Controls

### Objective

Productionize local deployment: rate limits, audits, observability.

---

## Phase 12 — Packaging, Release Docs & Demo Readiness

### Objective

Make the platform demoable and reviewable as a senior portfolio artifact.

---

## Phase Gate Checklist (Every Phase)

1. Deliverables complete locally
2. Acceptance criteria validated
3. Exclusions respected
4. Docs updated if contracts changed
5. Explicit approval before starting the next phase
