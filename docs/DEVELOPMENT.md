# Development Guide

## Repository layout

```text
backend/        FastAPI application, migrations and tests
frontend/       Next.js/TypeScript product UI
demo/knowledge  safe portfolio demo documents
docs/           current public engineering documentation
infrastructure/ deployment/observability placeholders
docker-compose.yml
Makefile
```

## Local setup

```bash
cp .env.example .env
docker compose up -d --build
```

Pull local models:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

## Common commands

```bash
make help
make test
make lint
make typecheck
make validate
```

Use `make validate` as the release gate. Do not weaken validation scripts simply to obtain a passing result.

## Migrations

```bash
docker compose exec backend alembic current
docker compose exec backend alembic heads
docker compose exec backend alembic upgrade head
```

Keep Alembic revision identifiers within the repository's existing version-column length constraint.

## Engineering rules

- preserve owner/admin authorization when adding new data access;
- prefer service/provider boundaries over infrastructure access from routes;
- use independent database sessions for worker jobs;
- keep long-running AI work outside web request lifecycles;
- make retries idempotent;
- persist safe operational metadata, not hidden reasoning or secrets;
- add regression tests for every production bug fixed;
- avoid introducing duplicate frontend component systems.

## Troubleshooting

### Backend unhealthy

```bash
docker compose logs --tail=200 backend
```

### Worker failure

```bash
docker compose logs --tail=200 worker
```

### Frontend failure

```bash
docker compose logs --tail=120 frontend
```

### Local auth refresh problems

Verify the browser/API use consistent loopback hostnames and check `.env.example`.

## Public repository hygiene

Historical implementation notes live under `docs/archive/development-history/`. Current product documentation should not depend on phase-numbered development files.
