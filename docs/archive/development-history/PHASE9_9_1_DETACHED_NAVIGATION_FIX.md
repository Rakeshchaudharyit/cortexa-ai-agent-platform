# Phase 9.9.1 — Execution Channel Reliability

## Problem

The Agent Runs launcher navigated away as soon as the backend emitted an agent run ID. In a browser, changing routes can tear down the fetch/SSE request even when the JavaScript iterator has not explicitly returned. The multi-agent coordinator currently runs inside that request and owns its database session. A torn-down request can therefore leave a run in `running` after the Conversation Agent task has already succeeded, while the final assistant response remains pending.

## Fix

The launcher now keeps the current page and execution channel mounted until the backend emits the terminal `complete` event. It then navigates to the finished durable run. If the stream ends without `complete`, it opens the durable run for recovery/inspection without starting another execution.

## Guarantees

- No duplicate agent run is started.
- The final assistant message is persisted before navigation.
- Run completion and response persistence remain part of one bounded transaction flow.
- Existing ownership, cancellation, approval, retry, safety, and execution-profile policies remain unchanged.
