# Phase 12.4 — Queue Monitoring, Dead-Letter Handling & Bulk Operations

Phase 12.4 hardens the background queue as an operational subsystem without moving new workloads.

## Dead-letter policy
Jobs that exhaust their configured attempts now transition to `dead_lettered`. Existing historical `failed` jobs remain visible and are also treated as dead-letter work for recovery purposes. Feature-owned resources (documents and evaluation runs) continue to use their existing terminal failure states.

## Safe requeue
Administrators can requeue only failed or dead-lettered jobs. Requeue clears transient execution state, resets attempts, clears cancellation and error fields, prepares the owning resource for another execution, commits the durable ledger first, and then publishes the job back to Redis.

## Bulk operations
The admin API supports bounded batches of up to 100 job IDs for cancellation or requeue. Ineligible or already-terminal jobs are skipped rather than mutated incorrectly.

## Queue health
The admin monitor exposes ready-list depth, delayed-retry depth, dead-letter count, stale running jobs, oldest queued age, worker heartbeat, and durable job history.

## Operational principle
PostgreSQL remains the source of truth. Redis is delivery infrastructure only. Requeue and recovery always start from the durable job ledger.
