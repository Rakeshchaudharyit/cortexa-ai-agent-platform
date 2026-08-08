# Cortexa Backend

FastAPI backend for the Cortexa AI Knowledge Platform.

## Responsibilities

- authentication and role-based APIs;
- documents, folders, lifecycle/versioning and citations;
- pgvector retrieval and grounded RAG;
- persistent streaming conversations;
- memories and safe built-in tools;
- RAG evaluation, feedback review and AI analytics;
- durable PostgreSQL job ledger and Redis-delivered background work;
- admin/system/audit APIs.

## Local development

Use the repository root Compose stack:

```bash
cp .env.example .env
docker compose up -d --build
```

Backend health/readiness:

```bash
curl -fsS http://localhost:18000/health
curl -fsS http://localhost:18000/ready
```

Development OpenAPI is available at `http://localhost:18000/docs`.

See the root [README](../README.md), [Architecture](../docs/ARCHITECTURE.md), [API Overview](../docs/API_OVERVIEW.md), and [RAG](../docs/RAG.md).
