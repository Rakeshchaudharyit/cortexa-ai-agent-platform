# Phase 9.6.1 — Live Run Reliability Fix

This patch addresses two browser-facing reliability gaps discovered during Phase 9.6 acceptance testing.

## Session restoration

Owned agent-run endpoints now use the shared authenticated request wrapper. A request that receives `401` performs the existing single-flight refresh flow and retries once with the renewed in-memory access token. This preserves the project's refresh-cookie architecture and avoids persisting access tokens in browser storage.

## Live run detail

The run-detail page polls only while a run is active. Polling stops automatically when the run reaches a terminal state and prevents overlapping requests. Existing run data remains visible during a temporary refresh failure.

## Retry visibility

The durable `task_retrying` event is now included in the safe activity timeline. No raw provider response, prompt, tool argument, memory content, or retrieved passage is exposed.
