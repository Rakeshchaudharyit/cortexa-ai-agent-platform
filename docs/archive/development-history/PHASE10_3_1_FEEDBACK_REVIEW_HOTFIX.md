# Phase 10.3.1 — Feedback Review Hotfix

Fixes HTTP 500 responses when an administrator marks feedback as reviewed or resolved.

The update endpoint now commits the requested state transition and then performs one explicit joined query for the persisted feedback, assistant message, and user. The response is built only from that freshly loaded row instead of reusing ORM instances across the commit boundary.

This also restores the real citation count in the returned admin item.
