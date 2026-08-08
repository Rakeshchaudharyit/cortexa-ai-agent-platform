# Phase 12.2 Validation

## Runtime acceptance

1. Confirm migration head is `0018_document_jobs`.
2. Confirm `backend`, `worker`, `redis`, `postgres`, `ollama`, and `frontend` are healthy.
3. Upload a supported document from the Documents page.
4. Confirm the HTTP request returns quickly with `pending`, a background job ID, and background processing mode.
5. Observe progress: queued, extracting, chunking, embedding, finalizing, ready.
6. Confirm the new version becomes active only after the job succeeds.
7. Refresh during execution and verify progress persists.
8. Queue a re-index and confirm the old active index remains usable until the atomic replacement succeeds.
9. Cancel an initial ingestion job and confirm the version becomes failed without partial chunks.
10. Restart the worker during execution and confirm durable recovery and bounded retry.

## Safety invariants

- The API request never extracts, chunks, or embeds in deployable environments.
- The worker uses independent database sessions.
- Existing chunks are deleted only after all replacement embeddings have been created.
- Duplicate concurrent ingestion/re-index requests are controlled with idempotency keys.
- Only successfully indexed versions become active for RAG.
