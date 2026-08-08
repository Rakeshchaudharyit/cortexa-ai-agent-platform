# Phase 11.1 — Enterprise Knowledge Management Foundation

Phase 11.1 extends the stable Chat/RAG product with document lifecycle controls and organization.

## Capabilities

- User-owned document folders with unique names.
- Folder-aware uploads and document filtering.
- Editable document title and tags.
- Archive and restore without deleting source files or embeddings.
- Archived documents are excluded from retrieval and automatic document-availability checks.
- Version-aware metadata (`version_number` and `supersedes_document_id`) for future replacement workflows.
- Folder deletion preserves documents by moving them to the unfiled state.
- Permanent deletion remains available as a separate destructive action.

## Retrieval safety

The shared retrieval service filters on both:

- `status = ready`
- `archived_at IS NULL`

This guarantees archived knowledge cannot be cited by Chat, direct RAG queries, or evaluations.

## Migration

`0015_knowledge_mgmt` creates `document_folders` and adds lifecycle and metadata columns to `documents`.

## Privacy

Folder names, titles and tags are user-owned metadata. No document content is duplicated into management tables.
