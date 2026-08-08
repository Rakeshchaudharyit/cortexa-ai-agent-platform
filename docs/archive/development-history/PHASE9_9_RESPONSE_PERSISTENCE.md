# Phase 9.9 — Response Persistence and Conversation Handoff

## Problem

The Agent Runs launcher navigated to the live run page as soon as the first
`agent_run_id` event arrived and returned from the SSE iterator. The streaming
HTTP request owns the backend request/session lifecycle that finalizes the
assistant message. Closing that iterator before the `complete` event could
leave the coordinated run visible while the related conversation contained a
streaming assistant row with no final content.

## Resolution

- Navigate to the live run detail page once the durable run identifier arrives.
- Continue consuming the same SSE stream through `run_completed`, final
  assistant persistence, metadata, and `complete`.
- Do not reopen or duplicate orchestration requests.
- Keep the conversation link unavailable while the run is active, displaying
  `Response pending…` instead.
- Enable `Open conversation` only after the run reaches a terminal state.

## Persistence contract

A successful coordinated response is considered delivered only after:

1. specialist execution returns final content;
2. the assistant message is finalized and committed;
3. the SSE `complete` event includes the persisted message;
4. the launcher stream reaches completion.

Run creation alone is not treated as response delivery.

## Privacy and security

The change does not store access tokens in browser storage, expose prompts in
run history, or alter existing ownership and refresh-cookie controls.
