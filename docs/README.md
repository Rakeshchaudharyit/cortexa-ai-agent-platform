# Docs

| Document | Description |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layered system design and Phase 5 stack boundaries |
| [AUTHENTICATION.md](AUTHENTICATION.md) | Auth flow, cookies, tokens, curl examples |
| [RAG.md](RAG.md) | Documents, embeddings, retrieval, grounded Q&A |
| [CONVERSATIONS.md](CONVERSATIONS.md) | Phase 5 persistent chat, streaming, edit/regenerate |
| [ROADMAP.md](ROADMAP.md) | Phases 0–13 with acceptance criteria |
| [SECURITY.md](SECURITY.md) | Local-first security model |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Coding standards, troubleshooting |

Project overview lives in the root [README.md](../README.md).

**Phase 5** implements persistent conversations, multi-turn RAG chat, SSE streaming, and the `/chat` UI on top of Phase 4 documents and Phase 3 authentication. Cross-conversation memory, agent tools, voice, and org/tenant management remain unavailable.
