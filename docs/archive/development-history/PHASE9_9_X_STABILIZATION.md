# Phase 9.9.x — Orchestration Stabilization

## Objective

Eliminate orchestration failures before adding capabilities. The release is based on the
runtime failure captured on 2026-08-04:

`sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called`

## Root cause

The SSE event callback committed the same request-scoped `AsyncSession` that the
coordinator was using while provider work and task transitions were active. Mid-run
transaction boundaries allowed ORM state to become invalid before the next transition,
leading to implicit asynchronous database I/O from ordinary attribute access.

## Stabilization changes

- SSE callbacks no longer commit or roll back the coordinator session.
- The coordinator creates explicit durable checkpoints only at safe boundaries:
  - run creation/classification,
  - validated task graph creation,
  - between completed specialist tasks,
  - terminal completion/failure through the caller commit.
- Task scalar fields are snapshotted before provider awaits.
- ORM task state is explicitly refreshed after provider awaits and timeout/error paths.
- Unexpected coordinator failures log exception type, message, correlation ID, and traceback.
- SSE lifecycle logs include event delivery, disconnect, and successful completion.
- A browser transport interruption reconnects to the durable owner-scoped run instead of
  starting a duplicate request.
- Failed transactions roll back before the coordinator reloads and marks the durable run
  terminal.

## Completion contract

A successful forced multi-agent request is complete only when all of the following hold:

1. The run has a terminal `completed` status.
2. The final Conversation Agent content is non-empty.
3. The assistant message is finalized and committed.
4. The SSE stream emits `complete` with both `agent_run_id` and the finalized message.
5. Refreshing the run or conversation does not lose the result.

## Privacy

Tracing records IDs, event types, durations, statuses, and exception classes only. It does
not log prompts, retrieved passages, memory content, tool arguments, credentials, or hidden
reasoning.
