# Deployment Guide

The included Docker Compose topology is the recommended local/demo deployment. Production should preserve the same service boundaries while replacing development defaults with managed infrastructure and secure configuration.

## Local portfolio deployment

### Prerequisites

- Docker Desktop / Docker Engine with Compose v2
- sufficient memory for PostgreSQL, Redis, Next.js, FastAPI and the selected Ollama models

### Configure

```bash
cp .env.example .env
```

Use the same browser hostname consistently (`localhost` or `127.0.0.1`) for the frontend/API pair so refresh-cookie behavior remains predictable.

### Start

```bash
docker compose up -d --build
```

### Pull models

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

### Verify

```bash
docker compose ps
curl -fsS http://localhost:18000/health
curl -fsS http://localhost:18000/ready
```

### Stop without deleting data

```bash
docker compose down
```

Do not add `-v` unless named-volume data should be permanently removed.

## Service responsibilities

| Service | Responsibility |
| --- | --- |
| frontend | Next.js product UI |
| backend | FastAPI HTTP/SSE API and migrations |
| worker | long-running durable jobs |
| postgres | relational data + pgvector embeddings |
| redis | queue delivery / heartbeat transport |
| ollama | local chat and embedding models |

## Production checklist

Before exposing a deployment publicly:

- terminate TLS/HTTPS at a trusted ingress or reverse proxy;
- generate a strong JWT secret and secure database credentials;
- set `APP_ENV=production`;
- use `AUTH_COOKIE_SECURE=true` and an appropriate cookie domain/SameSite policy;
- restrict `CORS_ALLOWED_ORIGINS` to deployed frontend origins;
- disable development password-reset token exposure/notices;
- use managed/monitored PostgreSQL and Redis where practical;
- move document storage to durable object storage or a backed-up persistent volume;
- configure database and document backups with restore testing;
- centralize logs and alert on readiness/worker/queue failures;
- provision workers independently from the API for workload scaling;
- keep FastAPI docs disabled in production unless intentionally protected/exposed;
- run `make validate` against the release candidate.

## Database migrations

The backend entrypoint applies `alembic upgrade head` before serving requests. Migration revision identifiers are intentionally kept within the existing Alembic version-column constraints.

Manual inspection:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic heads
```

## Backup considerations

At minimum back up:

- PostgreSQL data
- document object/file storage
- environment/secret configuration through the deployment secret manager (not the repository)

Redis is transport/cache infrastructure; durable job state remains in PostgreSQL.

## Scaling model

Scale request handling and long-running work independently:

- multiple API replicas behind an ingress/load balancer;
- one or more worker replicas consuming Redis-delivered jobs;
- shared PostgreSQL, Redis and document storage;
- provider capacity sized separately for chat and embeddings.


## Production portfolio topology

For the repository-provided HTTPS/same-origin production template, see [Live Demo Deployment](LIVE_DEMO_DEPLOYMENT.md). It uses `docker-compose.production.yml`, `Dockerfile.production` images, and Caddy as the public ingress.
