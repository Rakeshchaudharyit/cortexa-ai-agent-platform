# Phase 12.2 — Background Document Ingestion Jobs

## Architecture

Document upload requests now validate and store the binary, create the durable document/version record, enqueue a `document.ingestion` job, and return immediately. The worker owns extraction, chunking, embedding generation, and final activation.

PostgreSQL remains the source of truth for job and document state. Redis only transports ready work. The shared document storage volume is mounted by both API and worker services.

## Progress contract

- 0% — queued
- 10% — extracting text
- 30% — creating chunks
- 45–80% — generating embeddings
- 90% — finalizing index
- 100% — succeeded

## Retry and idempotency

Each upload receives an owner-scoped idempotency key derived from its immutable document-version ID. Re-index keys include the current processed timestamp, preventing duplicate concurrent re-indexing while allowing a later re-index after the document changes.

Chunks are prepared completely before the database swap. Existing chunks are deleted only inside the final transaction after all embeddings are available, so failed retries cannot leave partial or duplicated indexes.

## Cancellation

Queued jobs can be cancelled before execution. Running jobs check cancellation at each progress boundary. Initial ingestion cancellation marks that version failed; re-index cancellation preserves the existing ready index.

## Test-only behavior

The application test environment keeps deterministic inline processing for the pre-existing RAG integration suite. Development, staging, and production always use the worker-backed path.
