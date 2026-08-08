# Phase 12.1 Validation Notes

Completed in the build environment:

- Python syntax compilation across backend application and tests.
- Python AST parsing across all backend Python files.
- Docker Compose YAML parsing and worker dependency verification.
- Alembic revision-chain inspection with `0017_job_queue` as the only head.
- Revision identifier length validation for the existing `VARCHAR(32)` Alembic ledger.
- Frontend manifest JSON validation.
- Static regression checks for worker declaration, heartbeat, admin navigation, job monitor, cancellation, and durable-session ownership.

Requires the local Docker environment:

- Build and health checks for backend, worker, frontend, PostgreSQL, Redis, and Ollama.
- Alembic migration execution against the user's database.
- Browser validation of progress, cancellation, worker restart recovery, and idempotency.
