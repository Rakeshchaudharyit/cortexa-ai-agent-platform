# Phase 12.2.1 — Document Ingestion Finalization Hotfix

## Problem

Background ingestion successfully extracted, chunked, and embedded a document, then failed at 90% during the final PostgreSQL transaction. The worker stored only a generic `DBAPIError`, which hid the failing finalization step.

## Changes

- Validate embedding count, dimension, and finite values before database writes.
- Split finalization into explicit flush checkpoints:
  1. chunk/vector persistence,
  2. document ready-state metadata,
  3. active-version switching,
  4. lifecycle event and commit.
- Roll back the complete transaction when any checkpoint fails.
- Log the safe underlying database detail and full traceback.
- Persist stage-specific error codes in the background job ledger.
- Display a stage-specific ingestion failure message on the document.

## Safety

The new chunks, document status, version activation, and lifecycle event remain one atomic transaction. A failed re-index continues to preserve the previous usable index.
