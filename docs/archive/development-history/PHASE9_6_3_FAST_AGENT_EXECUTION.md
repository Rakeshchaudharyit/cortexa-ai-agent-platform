# Phase 9.6.3 — Fast Agent Execution

## Goal

Keep browser-launched multi-agent runs responsive on local Ollama hardware. Interactive runs must finish, degrade safely, or stop within a bounded window instead of waiting for several provider timeouts.

## Runtime policy

- Interactive run deadline: 90 seconds maximum.
- Normal specialist deadline: 35 seconds maximum.
- Conversation synthesis deadline: 20 seconds maximum.
- Timed-out tasks do not repeat in interactive fast mode.
- Independent configuration values may be lower, but older `.env` values cannot raise these interactive caps.
- Final synthesis uses the existing deterministic, citation-preserving fallback when the local provider is too slow.
- Plans are limited to four tasks in fast mode.

## Safety and compatibility

The fast path does not bypass ownership, approval gates, tool restrictions, state transitions, persistence, or redaction. It changes only execution budgets and user-visible progress.

## Browser experience

Active run pages show elapsed seconds. After 45 seconds, the UI explains that the local provider is slower than expected and that the run remains bounded.
