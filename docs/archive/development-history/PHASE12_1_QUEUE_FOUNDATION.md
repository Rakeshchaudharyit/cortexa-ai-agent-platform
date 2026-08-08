# Phase 12.1 — Background Queue Foundation

Phase 12.1 introduces a durable job execution layer without moving production workloads yet.

## Architecture

- PostgreSQL is the authoritative job ledger.
- Redis is delivery transport only.
- The API creates and inspects jobs.
- A separate worker container executes jobs with its own database sessions.
- Worker heartbeat is stored in Redis and displayed in the admin monitor.

## Guarantees

- Owner-scoped idempotency keys prevent duplicate submissions.
- Progress and terminal state are persisted.
- Running/queued/retrying jobs are recovered after worker or Redis restart.
- Cancellation is checked between bounded work steps.
- Retry backoff is bounded and persisted.
- The worker never uses request-scoped database sessions.

## Initial handler

`demo.validation` is intentionally harmless. It validates transport, progress updates,
job persistence, cancellation, worker health, and UI polling before real workloads are migrated.

## Deferred workloads

Document ingestion, embedding, evaluations, exports, and agent execution remain synchronous in
12.1. They will move to the queue incrementally in later Phase 12 milestones.
