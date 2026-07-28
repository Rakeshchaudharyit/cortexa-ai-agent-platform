# Roadmap

Cortexa AI Agent Platform — phased delivery plan.

Rules:

- Phases are sequential and audited.
- Do not implement future phases early.
- Do not ship placeholder business logic that pretends a feature exists.
- Each phase must pass local validation before the next phase starts.

---

## Phase 0 — Architecture & Engineering Foundation

**Status:** Current

### Objective

Establish the monorepo layout, documentation, environment contracts, Compose service plan, and engineering rules with zero application business logic.

### Deliverables

- Repository directories for backend, frontend, docs, scripts, sample-data, infrastructure
- Professional documentation (`README`, architecture, roadmap, security, development)
- `.gitignore`, `.env.example`, `docker-compose.yml`, `Makefile`
- Placeholder `pyproject.toml` and root `package.json`
- Named-volume Compose stubs for backend, frontend, postgres, redis, ollama

### Acceptance Criteria

- Directory tree matches the Phase 0 specification
- Documentation is complete and internally consistent
- `docker compose config` succeeds
- Python package markers compile (`compileall`)
- No secrets in the repository
- No fake feature implementations
- No git commit required from automation (operator decides)

### Exclusions

- FastAPI / Next.js application scaffolding
- Dependency installation
- Database schemas, migrations, auth, RAG, tools, speech, analytics

---

## Phase 1 — Backend Application Skeleton & Configuration

### Objective

Create a runnable FastAPI skeleton with typed settings, logging, health endpoint, and DI container wiring — still without AI features.

### Deliverables

- FastAPI app factory and router registration
- `core` settings loaded from environment
- Structured logging baseline
- `/health` (liveness) endpoint
- Dependency injection foundation for services/providers
- Backend Dockerfile (dev-oriented)
- Pytest smoke test for health

### Acceptance Criteria

- `uvicorn` serves health successfully in Docker or local venv
- Settings fail fast on invalid required config
- No Ollama, RAG, or agent business logic present
- Lint / type-check / unit smoke tests pass locally

### Exclusions

- Chat APIs, model providers, ORM entities beyond minimal infra if needed for app boot
- Frontend work
- Vector / speech integrations

---

## Phase 2 — Frontend Application Skeleton

### Objective

Scaffold a Next.js (App Router) + TypeScript application with layout shell, design tokens baseline, and API client stub pointed at the backend.

### Deliverables

- Next.js app under `frontend/`
- TypeScript strict configuration
- Base layout and empty dashboard shell (no fake metrics)
- Typed API client skeleton for health check
- Frontend Dockerfile (dev-oriented)
- Compose frontend service becomes buildable

### Acceptance Criteria

- `next dev` / container build succeeds
- UI loads and displays backend health status from real health endpoint
- No fabricated analytics widgets or mock agent chats presented as real

### Exclusions

- Full enterprise dashboard features
- Auth UI beyond placeholders if not yet backed by backend
- Direct browser calls to Ollama

---

## Phase 3 — Database Models, Migrations & Repositories

### Objective

Introduce PostgreSQL persistence with migrations, SQLAlchemy (or equivalent) models, and repository interfaces used by services.

### Deliverables

- Migration tooling and initial schema (identity/session/audit foundations as required)
- Repository implementations for introduced entities
- Redis connection provider for cache readiness
- Repository unit/integration tests against Compose Postgres

### Acceptance Criteria

- Migrations apply cleanly on empty database
- Services can persist/retrieve via repositories only
- API routes still do not touch the ORM session directly
- Tests pass with Dockerized Postgres

### Exclusions

- Vector store schema
- Agent reasoning loops
- Speech pipelines

---

## Phase 4 — Ollama Provider & Model Management

### Objective

Add an Ollama LLM provider behind a stable interface, plus model inventory/health checks.

### Deliverables

- `LLMProvider` protocol and `OllamaLLMProvider`
- Model list / pull status endpoints via services
- Configuration for default chat and embedding model names
- Provider-level tests with mocked HTTP or testcontainers where appropriate

### Acceptance Criteria

- Backend can list models from a running local Ollama
- No route imports Ollama client libraries directly
- Failure modes (Ollama down) return controlled API errors

### Exclusions

- Full chat UX
- RAG retrieval
- Tool calling loops

---

## Phase 5 — Chat / Agent Core Services

### Objective

Deliver core conversational and agent orchestration services with streaming responses and persisted turns.

### Deliverables

- Chat/agent service(s) with session continuity
- Streaming API (SSE or equivalent)
- Conversation persistence via repositories
- Frontend chat surface wired to real backend streams

### Acceptance Criteria

- End-to-end local chat works with Ollama-backed provider
- Conversations survive restart (Postgres)
- Architecture boundaries remain intact under review

### Exclusions

- Advanced multi-agent graphs
- External SaaS tools
- Speech I/O

---

## Phase 6 — Embeddings, Vector Store & RAG

### Objective

Add local embeddings, a vector store provider, document ingestion, and retrieval-augmented generation.

### Deliverables

- Embeddings provider (local via Ollama or dedicated local model)
- Vector store provider + persistence strategy
- Ingestion pipeline for approved file types
- RAG-enhanced chat path in services
- Upload validation hooks

### Acceptance Criteria

- Documents can be ingested and retrieved locally
- Chat answers can cite retrieved context when enabled
- Uploads rejected when validation fails

### Exclusions

- Cloud-hosted vector DBs as default
- Unbounded arbitrary code execution from documents

---

## Phase 7 — Memory System

### Objective

Implement short-term and long-term memory with privacy controls and explicit retention policies.

### Deliverables

- Memory service + provider abstractions
- Working memory for active sessions
- Longer-term memory write/read pathways
- Redaction / retention configuration
- Tests for isolation between tenants/sessions (as modeled)

### Acceptance Criteria

- Agents can recall prior relevant facts when policy allows
- Memory data remains local and inspectable
- Operators can clear or expire memory per policy

### Exclusions

- Cross-organization shared memory
- Training on user memory by default

---

## Phase 8 — Tool Calling Framework

### Objective

Add structured tool registration, permission gating, and audited execution.

### Deliverables

- Tool registry and JSON-schema style parameter contracts
- Permission model (allowlist / roles / session grants)
- Safe built-in tools (e.g., time, local search within sandbox)
- Audit events for tool invocations
- Frontend visibility into tool calls (where appropriate)

### Acceptance Criteria

- Models can request tools; runtime enforces permissions
- Denied tools never execute
- Audits record actor, tool, args hash/summary, outcome

### Exclusions

- Unsandboxed shell as a default tool
- Unrestricted network tools without explicit operator enablement

---

## Phase 9 — Speech (STT / TTS)

### Objective

Integrate local speech-to-text and text-to-speech providers.

### Deliverables

- STT and TTS provider interfaces + local implementations
- Upload/stream audio validation
- API endpoints and minimal UI controls
- Resource/timeout limits for audio jobs

### Acceptance Criteria

- Audio can be transcribed locally
- Text can be synthesized locally
- Cloud speech APIs are not required

### Exclusions

- Real-time telephony CPaaS
- Mandatory GPU cloud transcription

---

## Phase 10 — Enterprise Dashboard & Analytics

### Objective

Ship an operator dashboard with real metrics derived from local telemetry and persisted events.

### Deliverables

- Dashboard views: usage, model health, latency, error rates, tool audits
- Analytics aggregation jobs/services
- Role-aware UI sections (as auth model allows)

### Acceptance Criteria

- Charts/tables reflect real backend data (no fabricated demo numbers)
- Empty states are honest when no data exists
- Performance acceptable on local hardware

### Exclusions

- Third-party marketing analytics SDKs by default
- Fake KPI cards for screenshots

---

## Phase 11 — Hardening, Observability & Security Controls

### Objective

Productionize local deployment: security headers, rate limits, secrets handling, structured audits, and observability.

### Deliverables

- Rate limiting, CORS lockdown for local profiles
- Enhanced audit logging
- Prompt-injection mitigations at tool/RAG boundaries
- Metrics/tracing baselines under `infrastructure/observability`
- Security checklist verification against `SECURITY.md`

### Acceptance Criteria

- Security review items for local deploy are addressed or explicitly deferred with rationale
- Observability endpoints/dashboards documented
- Regression tests for authz and upload validation pass

### Exclusions

- Public internet multi-tenant SaaS hardening (out of local-first scope unless later expanded)

---

## Phase 12 — Packaging, Release Docs & Demo Readiness

### Objective

Make the platform demoable and reviewable as a senior portfolio artifact.

### Deliverables

- One-command local demo path documented and verified
- Sample data packs (non-secret) under `sample-data/`
- Architecture decision records as needed
- Final README polish, screenshots/recordings guidance
- Version tagging strategy (documentation only unless releasing)

### Acceptance Criteria

- Cold-start demo works on a clean machine meeting prerequisites
- Phase exclusions historically respected (no silent scope creep artifacts)
- Portfolio narrative aligns with implemented reality

### Exclusions

- Marketplace publication
- Unrelated greenfield features beyond the stated platform scope

---

## Phase Gate Checklist (Every Phase)

1. Deliverables merged/complete locally  
2. Acceptance criteria validated  
3. Exclusions respected  
4. Docs updated if contracts changed  
5. Explicit approval before starting the next phase
