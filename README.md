# Cortexa AI Agent Platform

Production-oriented, local-first AI Agent Platform designed as a flagship portfolio system for senior AI Engineer and AI Agent Developer roles.

Cortexa demonstrates enterprise software architecture applied to local AI runtimes: typed APIs, clean service boundaries, provider-isolated model integrations, and secure deployment patterns — without requiring cloud AI vendors.

> **Current status:** Phase 6 — Agent tools and function calling
>
> FastAPI, Next.js, PostgreSQL (+ pgvector), Redis, Ollama LLM/embeddings, authentication,
> document RAG, multi-turn chat, and built-in agent tools (calculator, datetime,
> knowledge search, conversation summary) are runnable.
>
> Cross-conversation long-term memory, external SaaS tools, voice, and organization/tenant
> management are **not** implemented.

See [docs/AGENT_TOOLS.md](docs/AGENT_TOOLS.md) for the Phase 6 tool architecture.

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

Phase 4 adds private document upload, local embeddings, pgvector retrieval, and grounded answers with citations. Phase 5 adds persistent conversations, multi-turn RAG chat (streaming and non-streaming), edit/regenerate, and the Next.js chat UI — on top of Phase 1–3 infrastructure and authentication.

---

## What Phase 5 Implements

| Capability | Status |
| --- | --- |
| Phase 1–4 foundation + auth + RAG | Preserved |
| Conversation CRUD, archive, search | Implemented |
| Multi-turn chat with RAG + history + rolling summary | Implemented |
| SSE streaming + citation events | Implemented |
| Edit latest user message / regenerate assistant | Implemented |
| Usage summary API | Implemented |
| `/chat` frontend (sidebar, composer, citations) | Implemented |
| Conversation tests + docs | Implemented |

## What Remains Unavailable

| Capability | Status |
| --- | --- |
| Cross-conversation / profile memory | Not implemented |
| Organization / tenant management | Not implemented |
| Social login / production password-reset email | Not implemented (dev reset CLI + in-app reset exist) |
| Agent tools / voice | Not implemented |
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

open http://localhost:13000/chat
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
| `GET /health`, `/health/live` | Liveness | `200` | Process-only; no dependency checks |
| `GET /ready`, `/health/ready` | Infra readiness | `200` / `503` | Postgres + migrations/schema + Redis |
| `GET /api/v1/system/info` | App info | `200` | `features.auth=true` |
| `POST /api/v1/auth/register` | Register | `201` | Sets HttpOnly refresh cookie |
| `POST /api/v1/auth/login` | Login | `200` | Sets HttpOnly refresh cookie |
| `POST /api/v1/auth/refresh` | Rotate refresh | `200` | Cookie required |
| `POST /api/v1/auth/logout` | Logout | `200` | Idempotent |
| `GET /api/v1/auth/me` | Current user | `200` | Bearer access token |
| `GET /api/v1/llm/status` | LLM diagnostics | `200` | Public |
| `POST /api/v1/llm/generate` | Non-streaming | `200` | **Requires auth** + pulled model |
| `POST /api/v1/llm/stream` | SSE streaming | `200` | **Requires auth** |
| `GET /api/v1/embeddings/status` | Embedding diagnostics | `200` | Public |
| `POST /api/v1/documents` | Upload document | `201` | **Requires auth**; sync ingest |
| `GET /api/v1/documents` | List documents | `200` | **Requires auth** |
| `POST /api/v1/rag/query` | One-shot grounded Q&A | `200` | **Requires auth** |
| `POST /api/v1/conversations` | Create conversation | `201` | **Requires auth** |
| `GET /api/v1/conversations` | List conversations | `200` | **Requires auth** |
| `POST /api/v1/conversations/{id}/messages` | Multi-turn chat | `200` | **Requires auth** |
| `POST /api/v1/conversations/{id}/messages/stream` | Streaming chat (SSE) | `200` | **Requires auth** |
| `GET /api/v1/usage/summary` | Usage aggregates | `200` | **Requires auth** |

Authentication details, password reset, and curl examples: [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

Development password-reset link (no real email):

```bash
docker compose exec backend \
  python -m app.cli.get_password_reset_link \
  --email user@example.com
```
Conversations, streaming, and RAG-in-chat: [docs/CONVERSATIONS.md](docs/CONVERSATIONS.md).
Documents and one-shot RAG: [docs/RAG.md](docs/RAG.md).

---

## Validation

```bash
make validate
```

This runs Compose config validation, secrets scan, backend pytest/ruff/mypy, frontend lint/typecheck/test/build, health/ready/system checks, auth + conversations smoke, frontend asset smoke, `.next` cache safety, and LLM status probe.

---

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md) | Auth flow, cookies, tokens, curl examples |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local workflow, troubleshooting |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phased plan |
| [docs/RAG.md](docs/RAG.md) | Documents, embeddings, retrieval |
| [docs/CONVERSATIONS.md](docs/CONVERSATIONS.md) | Phase 5 conversations & chat |
| [docs/SECURITY.md](docs/SECURITY.md) | Security posture |

---

## License

Proprietary — all rights reserved unless otherwise stated.
