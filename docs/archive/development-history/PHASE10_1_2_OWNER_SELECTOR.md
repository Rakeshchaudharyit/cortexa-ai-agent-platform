# Phase 10.1.2 — Evaluation Owner Selector

The RAG evaluation form no longer exposes raw user UUIDs. Administrators select an active user by name and email, with document counts shown to identify the correct private knowledge collection.

## Reliability

- The UI submits the selected user's UUID internally.
- Users with document collections are ordered first.
- Search filters users by name or email.
- The backend verifies that the selected owner still exists before creating the case.
- The selected owner remains selected after saving a case, which supports entering several evaluation cases for the same knowledge base.
