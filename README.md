# Cortexa AI Agent Platform

Production-oriented, local-first AI Agent Platform designed as a flagship portfolio system for senior AI Engineer and AI Agent Developer roles.

Cortexa demonstrates enterprise software architecture applied to local AI runtimes: typed APIs, clean service boundaries, provider-isolated model integrations, and secure deployment patterns — without requiring cloud AI vendors.

> **Current status:** Phase 0 — Architecture & Engineering Foundation  
> Application features are intentionally not implemented yet.

---

## Overview

Cortexa is a monorepo for a fully local AI agent stack. The long-term goal is a system that can:

- Run chat and agent workflows against local LLMs (Ollama + Qwen / Llama families)
- Ground responses with RAG over a local vector store
- Persist conversational and long-term memory
- Invoke tools under explicit permission controls
- Support speech-to-text and text-to-speech locally
- Expose an enterprise-grade operator dashboard with analytics
- Deploy with Docker, PostgreSQL, and Redis on a single machine

Phase 0 establishes repository layout, documentation, environment contracts, and Compose service planning only.

---

## Objectives

1. Prove a production-quality foundation suitable for audited, phase-gated delivery.
2. Enforce Clean Architecture, Dependency Injection, Repository Pattern, and Provider Pattern from day one.
3. Keep all AI execution local — no hidden cloud API calls by default.
4. Make every phase independently reviewable with clear acceptance criteria.

---

## Architecture Summary

```
Frontend (Next.js)
        ↓
FastAPI API Layer
        ↓
Service Layer (business logic)
        ↓
Provider Layer (external integrations)
        ↓
Local AI Runtime (Ollama) / Database / Vector Store / Memory / Speech
```

Routes never talk to Ollama or the database directly. Services own business rules. Providers own external systems. Repositories own persistence.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for diagrams and layer responsibilities.

---

## Technology Stack

| Layer | Technology | Version target |
| --- | --- | --- |
| Language (backend) | Python | 3.12 |
| API framework | FastAPI | latest stable |
| Language (frontend) | TypeScript | latest stable |
| Runtime (frontend) | Node.js | 22 LTS |
| UI framework | Next.js | latest stable |
| Primary database | PostgreSQL | 17 |
| Cache / queues | Redis | latest stable |
| Local LLM runtime | Ollama | latest stable |
| Orchestration | Docker Compose | v2 |
| Repo shape | Monorepo | `backend/` + `frontend/` |

Exact pinned package versions are introduced when application scaffolding begins (Phase 1+). Phase 0 only declares placeholders.

---

## Planned Capabilities

| Capability | Status |
| --- | --- |
| FastAPI backend | Planned |
| Next.js enterprise dashboard | Planned |
| Ollama + Qwen / Llama models | Planned |
| Local embeddings | Planned |
| RAG + vector database | Planned |
| Memory system | Planned |
| AI tool calling | Planned |
| Speech-to-text / text-to-speech | Planned |
| PostgreSQL + Redis | Planned |
| Analytics | Planned |
| Secure local Docker deployment | Planned |

None of the above are implemented in Phase 0.

---

## Development Phases

| Phase | Focus |
| --- | --- |
| 0 | Architecture & engineering foundation *(current)* |
| 1 | Backend application skeleton & configuration |
| 2 | Frontend application skeleton |
| 3 | Database models, migrations, repositories |
| 4 | Ollama provider & model management |
| 5 | Chat / agent core services |
| 6 | Embeddings, vector store & RAG |
| 7 | Memory system |
| 8 | Tool calling framework |
| 9 | Speech (STT / TTS) |
| 10 | Enterprise dashboard & analytics |
| 11 | Hardening, observability & security controls |
| 12 | Packaging, release docs & demo readiness |

Full detail: [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Local-First Philosophy

- Default execution path stays on the developer machine or private LAN.
- Model inference, embeddings, and speech processing target local runtimes.
- Cloud providers are opt-in only through explicit provider implementations and configuration — never implied.
- Sample data and secrets never leave the local environment unless the operator chooses otherwise.

---

## Security Philosophy

- No secrets in the repository; `.env.example` contains placeholders only.
- Least-privilege tool permissions for agent actions.
- Prompt-injection awareness at service and tool boundaries.
- Audit logging for sensitive operations.
- Upload validation and safe execution defaults.

See [docs/SECURITY.md](docs/SECURITY.md).

---

## Roadmap

Phase-gated delivery with objective, deliverables, acceptance criteria, and exclusions per phase.  
See [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Setup Prerequisites

Install before later phases:

- **Git** 2.40+
- **Docker Desktop** (or Docker Engine + Compose v2)
- **Python** 3.12
- **Node.js** 22 LTS
- **Make** (optional, for convenience targets)
- Sufficient disk for local models (Ollama images vary; plan several GB)

### Phase 0 (this phase)

No dependency installation is required. Validate structure and Compose syntax only:

```bash
make validate
```

Or manually:

```bash
docker compose config
python3 -m compileall backend
```

---

## Repository Layout

```
cortexa-ai-agent-platform/
├── backend/           # FastAPI application (scaffolded in later phases)
├── frontend/          # Next.js application (scaffolded in later phases)
├── docs/              # Architecture, roadmap, security, development standards
├── scripts/           # Operational and validation scripts
├── sample-data/       # Non-sensitive fixtures for later phases
├── infrastructure/    # Docker, reverse-proxy, and observability assets
├── docker-compose.yml # Planned local services
├── Makefile           # Developer convenience targets
├── pyproject.toml     # Backend / workspace Python metadata (placeholder)
├── package.json       # Frontend monorepo root metadata (placeholder)
└── .env.example       # Environment variable contract (no secrets)
```

---

## Engineering Rules (Non-Negotiable)

- Clean Architecture + SOLID
- Dependency Injection
- Repository Pattern for persistence
- Provider Pattern for every external integration
- Strong typing (Python type hints, TypeScript strict)
- Business logic only in Services
- API routes do not call Ollama, databases, or other externals directly

Coding standards: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## Documentation Index

| Document | Purpose |
| --- | --- |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System layers and diagrams |
| [ROADMAP.md](docs/ROADMAP.md) | Phased delivery plan |
| [SECURITY.md](docs/SECURITY.md) | Security model |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Coding and contribution standards |

---

## License

Proprietary portfolio project — rights reserved by the author unless otherwise stated in a future `LICENSE` file.
