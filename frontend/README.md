# Cortexa Frontend — Phase 4

See the repository root [README.md](../README.md) and [docs/RAG.md](../docs/RAG.md) for setup and document/RAG usage.

## Surfaces

- System status (health, readiness, LLM, feature flags)
- Auth (`/login`, `/register`, header session controls)
- Authenticated **Documents & grounded Q&A** panel on the home page

## API fetching decision

Uses **client-side fetching** for backend APIs.

Rationale:
- Browser calls use `NEXT_PUBLIC_API_BASE_URL` (host-reachable `http://localhost:8000` or remapped ports such as `18000`).
- Server-side fetch inside the frontend container would need a different internal URL (`http://backend:8000`).
- Client-side fetching keeps unavailable/offline states honest and avoids SSR crashes when the backend is down.
- Access tokens remain in memory only; refresh uses HttpOnly cookies (`credentials: "include"`).

## Docker development notes

- Compose bind-mounts `./frontend` into `/app` for hot reload.
- Container-owned volumes keep `/app/node_modules` and `/app/.next` inside Docker so host directories do not hide generated assets or installed dependencies.
