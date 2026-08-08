# Phase 9.6 — Agent Execution UX

Phase 9.6 makes coordinated multi-agent execution directly accessible from the browser while preserving the existing chat orchestration path.

## Architecture

The Agent Runs launcher reuses the authenticated conversation streaming API. This avoids a duplicate execution endpoint and keeps classification, planning, tool policy, memory, retrieval, approvals, cancellation, persistence, and SSE behavior behind one production path.

The launcher:

1. Creates an owner-scoped private conversation.
2. Streams the submitted objective through the existing chat service.
3. Detects the durable `agent_run_id` emitted by the orchestration lifecycle.
4. Navigates to the existing live run detail page.
5. Shows a safe explanation when the classifier selects ordinary chat instead of multi-agent execution.

## Privacy and safety

The launcher does not expose hidden reasoning, raw prompts from other users, retrieved passages, tool credentials, or provider payloads. Existing owner-scoped APIs and safe timeline metadata remain authoritative.

## Browser acceptance

- Agent Runs displays a **New Agent Run** action.
- The dialog validates non-trivial objectives.
- Starting a coordinated request opens its durable run detail page.
- Planning and task events continue through the existing timeline.
- Refresh preserves run state.
- Failure, approval, cancellation, and retry behavior remain available from the run detail view.
