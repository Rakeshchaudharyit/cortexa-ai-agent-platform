# RAG & Knowledge Retrieval

Cortexa provides owner-scoped document ingestion, local embeddings, pgvector retrieval, grounded answers, citation snapshots, document lifecycle/version control, and background indexing.

## Capabilities

| Capability | Behavior |
| --- | --- |
| Upload | `POST /api/v1/documents` accepts the file, creates durable document/job state, and returns while the worker processes it |
| Formats | `.txt`, `.md`, `.pdf`, `.docx` |
| Size limit | Configurable, 5 MiB by default |
| Ownership | Documents, chunks and retrieval are scoped to the authenticated owner |
| Embeddings | Provider abstraction; local default is Ollama `nomic-embed-text` (768 dimensions) |
| Retrieval | pgvector cosine similarity with configured similarity/top-k limits |
| Chat | Persistent multi-turn Document Knowledge mode with streaming and citation snapshots |
| Direct RAG | Grounded query endpoint for non-conversation workflows |
| Lifecycle | folders, archive/restore, immutable versions, active-version retrieval and lifecycle events |
| Re-index | queued background replacement of an existing index |
| Quality | evaluation cases, feedback, citation diagnostics, retrieval/latency analytics |

## Background ingestion

```mermaid
flowchart LR
    Upload[Upload accepted] --> Job[Durable ingestion job]
    Job --> Extract[Extract text]
    Extract --> Chunk[Create chunks]
    Chunk --> Embed[Generate embeddings]
    Embed --> Finalize[Atomic index finalization]
    Finalize --> Active[Ready / active for RAG]
```

The browser receives progress while work continues independently in the worker. Failed attempts can retry according to queue policy; finalization is atomic so a partial index is not activated.

## Version-aware retrieval

A logical knowledge document can have multiple immutable versions. Normal RAG retrieval uses only a version that is:

- owned by the requesting user;
- processing status `ready`;
- lifecycle state `active`;
- marked as the active version;
- not archived.

When a newer version is successfully published, the previous active version becomes superseded. A historical ready version can later be made active again.

## Retrieval quality controls

Before context reaches the model, the retrieval layer:

1. applies owner/document scope;
2. ranks vector matches;
3. removes exact/near-duplicate passages;
4. enforces the configured context-character budget using complete passages;
5. creates citation metadata only for context actually provided to the model;
6. validates answer citation markers against the final citation set.

## Safe no-answer behavior

When document retrieval is requested but no suitable context is available, Cortexa returns a bounded unavailable-information response with empty citations rather than asking the model to invent an answer.

General Chat mode is separate: when retrieval is intentionally disabled, the no-context RAG fallback does not apply.

## Conversation document scope

Conversation requests can use:

| `document_ids` | Retrieval behavior |
| --- | --- |
| omitted | eligible active documents owned by the user |
| `[]` | no retrieval / General Chat when enabled |
| non-empty list | only those owned eligible document versions |

## Citation persistence

Citations are persisted as snapshots with the assistant message. This keeps historical answers auditable even if document metadata or active versions change later.

## Re-indexing

Re-indexing runs in the background. The existing usable index is retained until replacement chunks/embeddings are prepared successfully. On success the replacement is finalized; on failure the previous usable index is preserved where applicable.

## Models

Pull local models explicitly:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

## Configuration

See `.env.example` for `DOCUMENT_*`, `CHUNK_*`, `EMBEDDING_*`, `RAG_*`, and provider settings.

## Current limitations

- text extraction only; scanned-image OCR is not included;
- local Compose uses filesystem document storage rather than cloud object storage;
- retrieval is primarily dense-vector based; hybrid keyword search/reranking can be added for a deployment that requires it;
- local Ollama response speed depends on host hardware and model availability.
