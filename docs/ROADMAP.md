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

**Status:** Complete

### Objective

Establish a production-quality, provider-neutral LLM layer with Ollama as the first provider.

### Deliverables

- `LLMProvider` protocol and Ollama implementation
- Typed settings for provider/model/timeouts/limits
- Non-streaming and streaming (SSE) generation APIs
- Dedicated LLM status endpoint (does not gate `/ready`)
- Deterministic tests with mocked HTTP / fake providers
- Minimal frontend LLM status display (no chat product)

### Exclusions

- Authentication
- RAG / embeddings
- Persistent memory
- Agent tools
- Voice
- Production chat UI / conversation history

---

## Phase 3 — Authentication and User Foundation

**Status:** Current

### Objective

Implement production-quality authentication and user foundation with JWT access tokens and HttpOnly refresh sessions.

### Deliverables

- User + refresh-session models and Alembic migration
- Argon2id password hashing
- Register / login / refresh / logout / me APIs
- Refresh-token rotation and reuse detection
- Auth dependencies protecting LLM generate/stream
- Minimal `/login` and `/register` frontend flow
- Comprehensive auth tests and documentation

### Exclusions

- RAG / document ingestion
- Conversation memory / agent tools / voice
- Organization or tenant management
- Social login / password-reset email delivery
- Admin dashboard / chat UI / API keys

---

## Phase 4 — Frontend Application Expansion

### Objective

Expand the status UI toward a durable application shell without fabricating dashboard metrics.

### Exclusions

- Full enterprise analytics dashboard
- Direct browser calls to Ollama

---

## Phase 5 — Database Models, Migrations & Repositories (domain expansion)

### Objective

Expand domain persistence beyond auth with additional repositories as product features arrive.

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
