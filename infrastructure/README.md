# Infrastructure

Docker, reverse-proxy, and observability assets for Cortexa.

| Path | Purpose |
| --- | --- |
| `docker/` | Extra Docker assets beyond root `docker-compose.yml` (Phase 1+) |
| `nginx/` | Optional reverse-proxy configs (hardening phases) |
| `observability/` | Metrics / tracing / logging stack definitions (Phase 11) |

Phase 0 keeps these directories reserved. Root Compose remains the local service plan.
