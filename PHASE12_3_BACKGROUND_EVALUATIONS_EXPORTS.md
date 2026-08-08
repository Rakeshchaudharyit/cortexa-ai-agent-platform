# Phase 12.3 — Background Evaluation & Export Jobs

Phase 12.3 moves RAG evaluation execution and evaluation CSV generation onto the durable Phase 12 queue foundation.

## Architecture

- PostgreSQL remains the authoritative job ledger.
- Redis is delivery transport only.
- The API creates an immutable evaluation-run record in `queued` state and returns immediately.
- The worker owns RAG evaluation execution with an independent database session.
- Progress is persisted through the background job ledger.
- CSV exports are generated in the shared document storage volume and downloaded only through an authenticated admin endpoint.
- Chat and interactive RAG remain unchanged.

## Job types

- `evaluation.run`
- `evaluation.export`

## Evaluation lifecycle

`queued -> running -> completed` with `failed` and `cancelled` terminal states.

## Export lifecycle

`queued -> running -> succeeded`; the job result contains only safe export metadata. Export files contain evaluation metrics and no retrieved passages, user prompts, hidden reasoning, or full answer content.

## Safety

Evaluation jobs are idempotent per run, exports are idempotent per evaluation run, cancellation is cooperative, and worker failures use bounded retries.
