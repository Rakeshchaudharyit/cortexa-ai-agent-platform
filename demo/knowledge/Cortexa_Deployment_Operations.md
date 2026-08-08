# Cortexa Deployment & Operations

The local development stack runs through Docker Compose. Services include frontend, backend, PostgreSQL with pgvector, Redis, Ollama, and a dedicated worker service.

The backend exposes health and readiness endpoints. Database schema changes are managed with Alembic. Long-running document ingestion, re-indexing, evaluation runs, and exports execute in the worker rather than inside browser request lifecycles.

Background job state is persisted in PostgreSQL while Redis is used for delivery. The operations console exposes worker health, queue depth, progress, retries, cancellation, dead-letter handling, and administrative requeue controls.
