# Live Demo Deployment

The repository includes a production-oriented single-host Docker topology in `docker-compose.production.yml`. It is intended as a repeatable portfolio deployment baseline, not a substitute for organization-specific cloud architecture.

## Topology

Caddy terminates HTTPS and serves one public hostname. `/api/*`, `/health` and `/ready` proxy to FastAPI; all other paths proxy to Next.js. PostgreSQL, Redis, Ollama and the worker are private to the Compose network.

## Host requirements

The full AI demo needs enough memory/CPU (or GPU where available) for the chosen Ollama chat and embedding models in addition to PostgreSQL, Redis, FastAPI, Next.js and the worker. Size the host from measured local usage rather than guessing.

## Deployment

```bash
cp .env.production.example .env.production
```

Replace every placeholder and set `PUBLIC_HOST` to a DNS name pointing at the server.

Validate before starting:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config
```

Start:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
```

Pull the model set once Ollama is healthy:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec ollama ollama pull qwen2.5:7b
docker compose --env-file .env.production -f docker-compose.production.yml exec ollama ollama pull nomic-embed-text
```

Verify:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps
curl -fsS https://YOUR_HOST/health
curl -fsS https://YOUR_HOST/ready
```

## Demo safety

- Use demo-only accounts and documents.
- Do not copy development `.env` or production customer data to the demo host.
- Keep `MULTI_AGENT_ENABLED=false`.
- Keep password reset disabled until a real delivery provider is implemented.
- Back up PostgreSQL and document storage before upgrades.
- Restrict SSH and server administration separately from the application.

## Rollback

Keep the previous image/tag and database backup available. Application containers can be rolled back independently, but database migrations must be reviewed for downgrade safety before reverting schema versions.
