# Phase 11.2 — Enterprise Knowledge Lifecycle & Version Control

Phase 11.2 separates a logical knowledge asset from its immutable uploaded versions.

## Data model

- `knowledge_documents` stores the logical asset, shared title/tags/folder, and active version.
- `documents` stores each immutable uploaded and indexed version.
- `knowledge_document_events` stores the append-only lifecycle audit timeline.

Existing documents are automatically migrated into logical knowledge assets. Existing supersedes chains are preserved as one lineage.

## Active-version retrieval

Only versions satisfying all of the following participate in RAG:

- owned by the authenticated user,
- ingestion status `ready`,
- not archived,
- `is_active_version = true`.

Publishing a successfully indexed new version atomically:

1. marks the previous active version as `superseded`,
2. marks the new version as `active`,
3. updates the logical asset's `active_version_id`,
4. records a lifecycle event.

A failed upload never replaces the current active version.

## User capabilities

- Publish a new immutable version from an existing document.
- View complete version history.
- Activate a historical ready version.
- Compare the latest two versions by metadata and indexing statistics.
- View the lifecycle timeline.
- Archive and restore versions.
- Rebuild chunks and embeddings for a version.
- Permanently delete one version while preserving the rest of the lineage.

## Lifecycle states

- `processing`
- `active`
- `superseded`
- `archived`
- `failed`

The ingestion status remains separate from lifecycle state. This avoids mixing processing health with publishing/governance state.

## Audit events

Events include document creation, version upload, version activation, metadata updates, archive/restore, re-index start/completion/failure, migration, and active-version reassignment.

Event metadata is bounded operational metadata. It does not store document content, embeddings, prompts, or hidden reasoning.

## API additions

- `GET /api/v1/documents/{id}/versions`
- `GET /api/v1/documents/{id}/timeline`
- `GET /api/v1/documents/{id}/compare/{other_id}`
- `POST /api/v1/documents/{id}/activate`
- `POST /api/v1/documents/{id}/reindex`

The existing upload endpoint accepts `supersedes_document_id` to create the next immutable version.

## Migration

Revision: `0016_doc_lifecycle`

The revision ID remains below the existing 32-character Alembic version-column limit.
