# Cortexa AI Agent Platform

Production-oriented, local-first AI Agent Platform designed as a flagship portfolio system for senior AI Engineer and AI Agent Developer roles.

Cortexa demonstrates enterprise software architecture applied to local AI runtimes: typed APIs, clean service boundaries, provider-isolated model integrations, and secure deployment patterns — without requiring cloud AI vendors.

> **Current status:** Phase 4 — Documents, Embeddings & RAG  
> FastAPI, Next.js, PostgreSQL (+ pgvector), Redis, Ollama LLM/embeddings, authentication, document ingestion, and grounded Q&A are runnable.  
> Product chat UI, memory, tools, voice, and organization/tenant management are **not** implemented.

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

Phase 4 adds private document upload, local embeddings, pgvector retrieval, and grounded answers with citations, on top of Phase 1–3 infrastructure and authentication.

---

## What Phase 4 Implements

| Capability | Status |
| --- | --- |
| Phase 1–3 foundation + auth | Preserved |
| Document upload (txt/md/pdf/docx, 5 MiB) | Implemented |
| Synchronous extract → chunk → embed | Implemented |
| pgvector storage + cosine retrieval | Implemented |
| Grounded RAG query + citations | Implemented |
| Embedding status API | Implemented |
| Authenticated Documents UI | Implemented |
| Document/RAG tests + docs | Implemented |

## What Remains Unavailable

| Capability | Status |
| --- | --- |
| Product chat UI / conversation history | Not implemented |
| Organization / tenant management | Not implemented |
| Social login / password-reset email | Not implemented |
| Memory / tools / voice | Not implemented |
| Analytics / admin modules | Not implemented |
| Automatic model downloads | Intentionally disabled |

---

## Quick Start (Docker)

```bash
cp .env.example .env
docker compose up -d --build

# Health (default example ports 8000/3000; this workspace may remap to 18000/13000)
curl -i http://localhost:18000/health
curl -i http://localhost:18000/ready
curl -i http://localhost:18000/api/v1/llm/status

# Pull models only when you want generation / embeddings to succeed
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text

curl -i http://localhost:18000/api/v1/embeddings/status

open http://localhost:13000
```

Stop:

```bash
docker compose down
```

---

## Architecture Summary

```
Frontend (Next.js)  →  FastAPI API  →  Services  →  DB / Redis / LLM providers
```

Routes never open database, Redis, or Ollama connections directly. The LLM factory injects the configured provider.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## Endpoint Semantics

| Endpoint | Purpose | Success | Notes |
| --- | --- | --- | --- |
| `GET /health` | Liveness | `200` | No dependency checks |
| `GET /ready` | Infra readiness | `200` / `503` | Postgres + Redis only |
| `GET /api/v1/system/info` | App info | `200` | `features.auth=true` |
| `POST /api/v1/auth/register` | Register | `201` | Sets HttpOnly refresh cookie |
| `POST /api/v1/auth/login` | Login | `200` | Sets HttpOnly refresh cookie |
| `POST /api/v1/auth/refresh` | Rotate refresh | `200` | Cookie required |
| `POST /api/v1/auth/logout` | Logout | `200` | Idempotent |
| `GET /api/v1/auth/me` | Current user | `200` | Bearer access token |
| `GET /api/v1/llm/status` | LLM diagnostics | `200` | Public |
| `POST /api/v1/llm/generate` | Non-streaming | `200` | **Requires auth** + pulled model |
| `POST /api/v1/llm/stream` | SSE streaming | `200` | **Requires auth** |

Authentication details and curl examples: [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

---

## Validation

```bash
make validate
```

This runs Compose config validation, secrets scan, backend pytest/ruff/mypy, frontend lint/typecheck/test/build, health/ready/system checks, auth smoke, frontend asset smoke, and LLM status probe.

---

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) | Auth flow, cookies, tokens, curl examples |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local workflow, troubleshooting |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phased plan |
| [docs/SECURITY.md](docs/SECURITY.md) | Security posture |

---

## License

Proprietary — all rights reserved unless otherwise stated.
