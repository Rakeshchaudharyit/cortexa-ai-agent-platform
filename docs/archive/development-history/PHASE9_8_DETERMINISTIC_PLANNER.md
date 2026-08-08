# Phase 9.8 — Deterministic Planner First

## Objective

Remove LLM planning from the critical path for common interactive agent runs while preserving an LLM fallback for genuinely ambiguous workflows.

## Architecture

`DeterministicPlanningEngine` is a provider-neutral, side-effect-free planning policy. It consumes safe request signals, classifier capabilities, enabled tools, selected documents, memory state, and execution profile. It returns a validated `AgentPlan` or `None`.

The Planning Specialist now evaluates strategies in this order:

1. Phase 9.8 deterministic planning engine.
2. Existing compatibility templates for historical classifier reason codes.
3. LLM planner for ambiguous requests when a provider is available.
4. Safe conversation-only fallback.

## Supported deterministic workflows

- Knowledge review → Conversation synthesis
- Knowledge review → Tool calculation/lookup → Conversation synthesis
- Memory retrieval → Knowledge review → Conversation synthesis
- Approval-gated memory proposal when explicitly requested and within the four-task interactive cap
- Direct conversation fallback for requests with no reliable specialist signal

## Reliability guarantees

- A plan always contains at least one task.
- Every plan ends with a Conversation task.
- Common forced browser runs do not call the planner LLM.
- Fast-profile tasks have zero timeout retries.
- Interactive deterministic plans are capped at four tasks.
- Only enabled tools may be scheduled.
- The planning strategy and planning duration are emitted as safe event metadata.
- No hidden reasoning, prompts, document passages, or tool arguments are stored in planning telemetry.

## Expected result

The common "review available knowledge and recommend an implementation" workflow should create a two-task plan immediately: Knowledge → Conversation. Planning latency should be milliseconds rather than tens of seconds.
