# Multi-Agent Observability (Phase 9.5)

Phase 9.5 adds durable, content-free telemetry to the multi-agent runtime. The
telemetry layer is passive: it observes lifecycle boundaries but never controls
planning, dispatch, retries, approval, cancellation, or state transitions.

## Persisted run metrics

- total run duration
- planning duration
- summed task execution duration
- fallback synthesis duration when used
- steps consumed
- LLM calls consumed
- tool calls consumed
- maximum observed context characters
- correlation ID and stable safe error code

All new fields are additive. Existing runs remain valid because phase durations
are nullable and counters default to zero.

## Privacy boundary

Telemetry must not receive or persist:

- prompts or assistant responses
- retrieved document passages
- memory values
- tool arguments or raw tool output
- provider payloads, tokens, credentials, or stack traces
- hidden reasoning

Public event metadata continues through the explicit allowlist in
`app.agents.api.safe_metadata`.

## Operational use

The metrics support run-level diagnosis, budget analysis, timeout investigation,
and future aggregate admin dashboards without weakening ownership or exposing
user content.
