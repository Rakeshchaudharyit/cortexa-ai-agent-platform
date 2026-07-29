# Docs

| Document | Description |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layered system design and Phase 3 auth + LLM boundaries |
| [AUTHENTICATION.md](AUTHENTICATION.md) | Auth flow, cookies, tokens, curl examples |
| [ROADMAP.md](ROADMAP.md) | Phases 0–12 with acceptance criteria |
| [SECURITY.md](SECURITY.md) | Local-first security model |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Coding standards, troubleshooting |

Project overview lives in the root [README.md](../README.md).

**Phase 3** implements authentication (JWT access + HttpOnly refresh rotation) and protects LLM generate/stream. Chat UI, RAG, memory, tools, voice, and org/tenant management remain unavailable.
