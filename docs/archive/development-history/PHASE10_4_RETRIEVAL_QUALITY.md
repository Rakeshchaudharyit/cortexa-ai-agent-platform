# Phase 10.4 — Retrieval Quality Improvements

Phase 10.4 strengthens the stable Chat/RAG path without adding a new database migration.

## Delivered

- Stable exact and near-duplicate passage removal before context construction.
- Ranked, complete-passage context selection under the configured RAG character budget.
- Citation/context alignment: citations are generated only for passages actually sent to the model.
- Invalid model-generated citation markers are removed when they reference unavailable citations.
- Safe retrieval diagnostics record candidate, selected, removed, and context-character counts.
- Regression coverage for near-duplicate removal, budget selection, and citation validation.

## Design constraints

- No LLM call is used for deduplication or context selection.
- Retrieval ranking order is preserved.
- Passages are not silently cut in the middle to fill the final few characters.
- User prompts, document passages, credentials, and hidden reasoning are not added to logs.
- Existing RAG and conversation APIs remain backward compatible.

## Expected impact

- Less repetitive context sent to the model.
- Lower prompt size and faster local generation.
- Fewer duplicate or conflicting citations.
- No citation card for a passage excluded from the model context.
- Better regression signals in Phase 10.1 evaluations and Phase 10.2 observability.
