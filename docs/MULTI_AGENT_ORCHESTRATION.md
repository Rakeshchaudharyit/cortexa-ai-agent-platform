# Multi-Agent Orchestration (Phase 9)

**Status:** Phase 9.1 foundation + Phase 9.2 bounded execution intelligence implemented (backend).  
**Public APIs / SSE / approval UI:** not implemented (Phase 9.3).  
**Migration:** `0011_multi_agent_orchestration`

This document describes what is implemented today. Design history remains in
[`MULTI_AGENT_ORCHESTRATION_DESIGN.md`](./MULTI_AGENT_ORCHESTRATION_DESIGN.md).

---

## Phase 9.1 — Foundation (complete)

- `AgentDefinition`, `AgentRun`, `AgentTask`, `AgentHandoff`, `AgentApproval`, `AgentRunEvent`
- Run / task / approval enums and explicit state transitions
- `AgentRegistry` with seven system agents: coordinator, planning, conversation,
  knowledge, memory, tool, safety
- Server-side plan validation (registered agents, deps, cycles, depth, tools)
- Repository layer with ownership checks
- `AgentContextEnvelope` with character budgets
- Phase 9 settings (`MULTI_AGENT_ENABLED`, task/step/timeout/retry budgets)
- Seeded agent definitions via migration `0011`

---

## Phase 9.2 — Execution intelligence (complete)

### Complexity classifier

Module: `backend/app/agents/classifier.py`

- Deterministic first: greetings, explanations, rewrites, single calculator /
  datetime / document lookup / memory lookup stay **single-agent**
- Multi-agent only when at least two distinct specialist capabilities or
  dependent operations are required
- Message length alone never triggers multi-agent
- Bounded model-assisted classification only when deterministic signals are
  ambiguous; provider failure falls back to single-agent
- Output: `AgentComplexityDecision` (execution mode, confidence, reason codes,
  capabilities, suggested agents, planning/approval flags, safe summary)

### Planning Agent

Module: `backend/app/agents/specialists/planning.py`

- Deterministic templates for common combos:
  - knowledge + tool + conversation
  - memory + knowledge + conversation
  - knowledge + tool + memory proposal + conversation
  - knowledge + conversation (recommend)
- LLM planning only when no template matches
- Every plan validated through `AgentRegistry.validate_plan`
- One replan attempt when configured (`AGENT_MAX_REPLANS`)
- Safe `reasoning_summary` only — no hidden chain-of-thought
- No tool execution, memory writes, or document content access beyond planning metadata

### Coordinator engine

Module: `backend/app/agents/coordinator.py`

- Classifies → single-agent fallback **or** multi-agent run
- Simple requests: **no** `AgentRun` row; preserve existing chat latency path
- Multi-agent: create run → planning → safety → persist tasks → sequential
  dependency-ordered execution → conversation synthesis → finalize
- Persists transitions, handoffs, and internal run events
- Parallel read-only tasks remain disabled
- No background jobs; execution is in-process for Phase 9.2

### Specialist agents

| Agent | Module | Role |
|-------|--------|------|
| Conversation | `specialists/conversation.py` | Ordinary chat + final synthesis |
| Knowledge | `specialists/knowledge.py` | Owned RAG retrieval, citations, untrusted injection marking |
| Memory | `specialists/memory.py` | Approved reads; writes return approval-required internally |
| Tool | `specialists/tool_agent.py` | Allow-listed tools via `ToolExecutor` |
| Safety | `specialists/safety.py` | Deterministic policy gate + optional model assist |

Execution contract schemas: `AgentExecutionInput` / `AgentExecutionResult` in
`agents/schemas.py`. Outputs are bounded by `AGENT_TASK_OUTPUT_MAX_CHARACTERS`.

### Safety

- Deterministic checks are authoritative (unknown agents, unauthorized/disabled
  tools, shell/SQL/code, system-prompt extraction, cross-user access, unsupported
  externals, persistent writes → approval required)
- Document prompt injection is treated as **untrusted data**, never as instructions
- Model-assisted review only for ambiguous cases; provider failure fails closed

### Dependency execution, retries, timeouts, budgets

- Tasks run only when dependencies succeeded (or soft-succeeded with approval)
- Failed dependency → child skipped
- Retryable: transient provider/retrieval failures (bounded by `AGENT_MAX_RETRIES`)
- Non-retryable: ownership, validation, policy, invalid tool args, approval required
- `asyncio.wait_for` task timeout (`AGENT_TASK_TIMEOUT_SECONDS`)
- Run timeout via `RunBudget` (`AGENT_RUN_TIMEOUT_SECONDS`)
- Pre-flight budgets for steps, LLM calls, tool calls, context characters

### Handoffs and internal events

- `AgentHandoff` persisted on meaningful responsibility changes
- `AgentRunEvent` timeline: `run_started`, `complexity_classified`,
  `planning_started`, `plan_created`, `safety_checked`, `task_*`, `handoff`,
  `approval_required`, `run_completed` / `run_failed` / `run_timed_out`
- Metadata is safe and bounded — no raw prompts, passages, or secrets

### Chat integration (feature-gated)

- `MultiAgentService` (`agents/multi_agent.py`) + `MULTI_AGENT_ENABLED`
- Wired on app state and optionally on `ChatService`
- Phase 9.2 tests call the coordinator / service directly
- Existing simple chat and streaming paths remain the default for ordinary turns
- Auto public multi-agent progress streaming is **not** enabled yet

### Fake provider support

`FakeLLMProvider` continues to support scripted turns for valid/invalid plans,
safety allow/block, specialist responses, timeouts, and malformed JSON via
`scripted_turns` / `fail_mode` / `turn_factory`.

---

## Limitations (Phase 9.2)

- No public agent-run APIs
- No public approval or cancellation endpoints
- No SSE multi-agent progress events to the frontend
- No `/agent-runs` UI, approval UI, or admin agents UI
- Limited read-only parallelism disabled
- Chat does not blindly route all production traffic through multi-agent
- Approval-required memory writes are represented internally only

---

## Phase 9.3 — Pending

- Agent-run public APIs and ownership-scoped listing
- Approval public APIs and resolution flow
- Cancel endpoint
- SSE multi-agent event stream compatible with existing chat SSE
- Frontend agent-run pages and approval UI
- Admin agents / agent-runs pages

---

## Observability

Safe structured logs may include: `run_id`, `task_id`, `execution_mode`,
classifier reason codes, `agent_key`, plan task count, task status, retry count,
LLM/tool call counts, context characters, `duration_ms`, safety decision,
`error_code`, `correlation_id`.

Never logged: full user prompts, full plans, raw document/memory content,
secret-bearing tool arguments, hidden reasoning, tokens/cookies.
