# Phase 9.5.2 — Failure Classification and Retry Policy

Phase 9.5.2 centralizes multi-agent failure decisions in `app.agents.failures`.
The coordinator no longer maintains provider-specific retry code lists.

## Categories

- `transient`: temporary provider, retrieval, connection, or rate-limit failures.
- `timeout`: bounded task, provider, or tool timeout.
- `permanent`: missing models, agents, tools, documents, or failed dependencies.
- `validation`: malformed plans, arguments, responses, or user-controlled input.
- `policy`: safety, permission, disabled-feature, or confirmation restrictions.
- `limit`: configured execution, memory, or result-size budget exceeded.
- `cancellation`: user or system cancellation.
- `internal`: unknown failures that are not safe to retry automatically.

Only transient and timeout failures are retryable. Retries remain bounded by the
smaller of the task plan limit and the global `agent_max_retries` setting.

## Safety and privacy

Classification uses exception types, stable error codes, retry hints, and safe
messages only. It never inspects or persists prompts, retrieved passages,
memory content, tool arguments, credentials, or provider payloads.

## Timeline diagnostics

Each retry now emits a `task_retrying` event with only safe metadata:

- failure category
- stable error code
- retry decision
- retry reason
- attempt number
- configured maximum retries
