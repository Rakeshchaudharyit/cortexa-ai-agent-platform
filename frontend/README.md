# Cortexa Frontend — Phase 1

See the repository root [README.md](../README.md) for setup and validation.

## API fetching decision

Phase 1 uses **client-side fetching** for `/health`, `/ready`, and `/api/v1/system/info`.

Rationale:
- Browser calls use `NEXT_PUBLIC_API_BASE_URL` (host-reachable `http://localhost:8000`).
- Server-side fetch inside the frontend container would need a different internal URL (`http://backend:8000`), which complicates local Compose without adding dual config in Phase 1.
- Client-side fetching keeps unavailable/offline states honest and avoids SSR crashes when the backend is down.

## Docker development notes

- Compose bind-mounts `./frontend` into `/app` for hot reload.
- Container-owned volumes keep `/app/node_modules` and `/app/.next` inside Docker so host directories do not hide generated assets or installed dependencies.
