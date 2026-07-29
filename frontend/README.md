# Cortexa Frontend — Phase 5

See the repository root [README.md](../README.md), [docs/RAG.md](../docs/RAG.md), and [docs/CONVERSATIONS.md](../docs/CONVERSATIONS.md) for setup, documents, and chat.

## Surfaces

- System status (health, readiness, LLM, feature flags)
- Auth (`/login`, `/register`, header session controls)
- Authenticated **Documents & grounded Q&A** panel on the home page
- **Chat** (`/chat`, `/chat/[conversationId]`) — conversation sidebar, message list, streaming composer, citations

## API fetching decision

Uses **client-side fetching** for backend APIs.

Rationale:
- Browser calls use `NEXT_PUBLIC_API_BASE_URL` (host-reachable `http://localhost:8000` or remapped ports such as `18000`).
- Server-side fetch inside the frontend container would need a different internal URL (`http://backend:8000`).
- Client-side fetching keeps unavailable/offline states honest and avoids SSR crashes when the backend is down.
- Access tokens remain in memory only; refresh uses HttpOnly cookies (`credentials: "include"`).
- Conversation streaming uses `fetch` + `ReadableStream` in `services/conversations.ts` so SSE requests can send the bearer token (unlike `EventSource`).

## Docker development notes

- Compose bind-mounts `./frontend` into `/app` for hot reload.
- Container-owned volumes keep `/app/node_modules` and `/app/.next` inside Docker so host directories do not hide generated assets or installed dependencies.
