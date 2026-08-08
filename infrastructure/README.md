# Infrastructure

Infrastructure assets for Cortexa AI Knowledge Platform.

- `docker-compose.yml` — local development/demo topology with bind-mounted Next.js development runtime.
- `docker-compose.production.yml` — production-oriented single-host topology with private PostgreSQL/Redis/Ollama services, independent worker, standalone Next.js image and Caddy HTTPS ingress.
- `Caddyfile` — same-origin routing for the public frontend and `/api/*` FastAPI endpoints.
- `frontend/Dockerfile.production` — standalone Next.js production image.
- `backend/Dockerfile.production` — FastAPI runtime image without development/test dependencies.

See [Deployment Guide](../docs/DEPLOYMENT.md) and [Live Demo Deployment](../docs/LIVE_DEMO_DEPLOYMENT.md).
