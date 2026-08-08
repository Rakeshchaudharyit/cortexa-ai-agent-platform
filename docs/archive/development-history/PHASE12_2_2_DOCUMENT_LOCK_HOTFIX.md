# Phase 12.2.2 — Document Lock Hotfix

## Root cause

Background ingestion reached the 90% finalization boundary and then failed with a raw DBAPIError. `Document.folder` is configured with joined loading, so `select(Document).with_for_update()` implicitly added a nullable outer join to `document_folders`. PostgreSQL does not allow `FOR UPDATE` to lock the nullable side of an outer join.

## Fix

The finalization query now disables the joined folder load and scopes the row lock to the `documents` table only:

- `lazyload(Document.folder)`
- `with_for_update(of=Document)`

No schema or migration change is required.

## Regression guarantee

The worker still takes a row-level lock on the target document before swapping chunks and activating the version, but unrelated optional relationships are no longer part of the locking statement.
