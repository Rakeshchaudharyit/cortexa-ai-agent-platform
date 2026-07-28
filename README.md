# Cortexa AI Agent Platform

Production-oriented, local-first AI Agent Platform designed as a flagship portfolio system for senior AI Engineer and AI Agent Developer roles.

Cortexa demonstrates enterprise software architecture applied to local AI runtimes: typed APIs, clean service boundaries, provider-isolated model integrations, and secure deployment patterns — without requiring cloud AI vendors.

> **Current status:** Phase 2 — Local LLM Provider and Ollama Integration  
> FastAPI, Next.js, PostgreSQL, Redis, and an Ollama LLM provider layer are runnable.  
> Chat UI, RAG, memory, tools, voice, and authentication are **not** implemented.

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

Phase 2 delivers a provider-neutral LLM abstraction with Ollama status, non-streaming generation, and SSE streaming — without a product chat UI.

---

## What Phase 2 Implements

| Capability | Status |
| --- | --- |
| Phase 1 foundation (health/ready/system UI) | Preserved |
| Provider-neutral `LLMProvider` interface | Implemented |
| Ollama provider (tags + chat + stream) | Implemented |
| `GET /api/v1/llm/status` | Implemented |
| `POST /api/v1/llm/generate` | Implemented |
| `POST /api/v1/llm/stream` (SSE) | Implemented |
| Controlled missing-model behavior | Implemented |
| Minimal frontend LLM status panel | Implemented |
| Mocked/fake provider tests | Implemented |

## What Remains Unavailable

| Capability | Status |
| --- | --- |
| Product chat UI / conversation history | Not implemented |
| Authentication / users / orgs | Not implemented |
| RAG / embeddings / vector search | Not implemented |
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

# Pull the default model only when you want generation to succeed
docker compose exec ollama ollama pull qwen2.5:7b

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
| `GET /api/v1/system/info` | App info | `200` | `features.ollama=true` |
| `GET /api/v1/llm/status` | LLM diagnostics | `200` | Missing model is not a crash |
| `POST /api/v1/llm/generate` | Non-streaming | `200` | Requires pulled model |
| `POST /api/v1/llm/stream` | SSE streaming | `200` | `text/event-stream` |

---

## Validation

```bash
make validate
```

This runs Compose config validation, secrets scan, backend pytest/ruff/mypy, frontend lint/typecheck/test/build, health/ready/system checks, frontend asset smoke, and LLM status probe.

---

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local workflow, LLM curl examples, troubleshooting |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phased plan |
| [docs/SECURITY.md](docs/SECURITY.md) | Security posture |

---

## License

Proprietary — all rights reserved unless otherwise stated.
