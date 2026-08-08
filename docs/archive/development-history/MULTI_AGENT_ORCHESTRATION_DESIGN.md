# Phase 8 — Multi-Agent Orchestration Framework (Design Only)

**Status:** Design / pre-implementation  
**Does not change the live product milestone.** Phase 7 (Long-Term Memory) remains the current implemented milestone until Phase 8 is coded, validated, and committed separately.  
**Expected migration (when implemented):** `0009_multi_agent_orchestration` — **not created in this design pass.**

---

## 1. Purpose

Transform the current single `AgentOrchestrator` chat path into a **controlled multi-agent architecture** that can delegate bounded tasks to specialized agents, while remaining:

- provider-neutral (fake provider + Ollama)
- user-owned and audited
- depth-, step-, and budget-bounded
- incapable of unrestricted autonomous loops
- compatible with existing conversation, RAG, memory, and tool layers

This document is the architecture contract for implementation. No Phase 8 application code is included here.

---

## 2. Current architecture assessment

Today (Phase 6–7):

| Layer | Role |
|-------|------|
| `ChatService` | Authz, conversation ownership, retrieval mode, streaming SSE, persistence |
| Memory (`app/memory`) | Explicit intent, retrieval, suggestions/extraction, settings |
| RAG | Document-scoped retrieval and citations |
| `AgentOrchestrator` | Single tool-calling LLM loop with max iterations |
| `ToolRegistry` / `ToolExecutor` | Server-registered tools, permission checks, audit rows |
| Conversation history / summary | Distinct from memory and RAG |

Gaps for multi-agent work:

- One orchestrator owns planning *and* execution without typed agent roles.
- No durable agent-run / task / handoff / approval entities.
- No registry of specialized agents analogous to tools.
- No first-class approval pause for sensitive writes beyond memory confirmation.
- Streaming events are tool/memory oriented; agent-plan/task lifecycle is not yet modeled.

Fallback requirement: **simple requests continue to use a Conversation Agent–only path** (or today’s single-orchestrator equivalent) without creating multi-agent runs.

---

## 3. Proposed architecture

```
Authenticate + load conversation (ownership)
        │
        ▼
Complexity classifier (deterministic + optional LLM assist)
        │
        ├─ simple ──► Conversation Agent only ──► persist assistant message
        │
        └─ complex ──► create AgentRun
                          │
                          ▼
                    Planning Agent → AgentPlan (structured)
                          │
                          ▼
                    Registry.validate_plan()
                          │
                          ▼
                    Safety Agent review
                          │
              ┌───────────┴───────────┐
              │ reject / require approval│
              ▼                       ▼
         fail safely            execute tasks
                                   │
                    sequential by default;
                    limited parallel read-only when marked safe
                                   │
                    persist AgentTask transitions
                    stream AgentRunEvent
                    pause on AgentApproval when required
                                   │
                          Coordinator merges results
                                   │
                          Conversation Agent final response
                                   │
                          finalize AgentRun + audits
```

**One coordinator owns each execution.** Specialized agents never spawn uncontrolled peer orchestrators.

---

## 4. Agent responsibilities

### 4.1 Coordinator Agent

- Receives the user request and run context.
- Decides single-agent vs multi-agent handling.
- Creates/accepts a bounded plan.
- Delegates only to **registered** agents.
- Merges task outputs under context budgets.
- Enforces max steps, depth, timeouts, and call budgets.
- Requests final response synthesis (usually Conversation Agent).

### 4.2 Planning Agent

- Decomposes complex requests into `AgentPlan` / `AgentPlanTask`.
- **Cannot** execute tools, modify memory, or call external systems.
- Plans only from registered agent capabilities and allowed tools.
- Emits a brief user-safe `reasoning_summary` (never hidden chain-of-thought).

### 4.3 Conversation Agent

- Default path for ordinary chat.
- Synthesizes the final user-visible answer.
- Applies current user instruction using approved context only.

### 4.4 Knowledge Agent

- Performs document retrieval and citation validation.
- Summarizes authorized passages.
- Never accesses another user’s documents.
- Does not write memories.

### 4.5 Memory Agent

- Retrieves approved memories.
- Proposes or applies remember/forget/update **only through MemoryService**.
- Honors confirmation / global / conversation memory policies.
- Cannot bypass sanitizer or ownership.

### 4.6 Tool Agent

- Invokes tools exclusively via `ToolExecutor` + `ToolRegistry`.
- Cannot call unregistered tools or invent tool names.
- Reuses existing tool audit mechanisms.

### 4.7 Safety Agent

- Evaluates plans and sensitive actions.
- Detects policy violations and prompt-injection attempts in retrieved content.
- Blocks or requires approval; never silently alters user data.

---

## 5. Registry design

Mirror the tool registry pattern.

### `BaseAgent`

- `name`, `description`, `version`, `capabilities`
- `allowed_tools: frozenset[str]`
- `maximum_steps`, `timeout_seconds`
- `can_handle(task) -> bool`
- `validate_task(task) -> None`
- `build_context(envelope) -> AgentContext`
- `execute(task, context) -> AgentTaskResult`

### `AgentRegistry`

- `register(agent)` — reject duplicates / unknown imports
- `get(name)`, `list()`, `enabled_agents()`
- `validate_plan(plan)` — names, deps, cycles, depth, task count, tools, approvals

**Hard rules**

- Server-side registration only at startup.
- No runtime arbitrary imports, user-supplied Python paths, or dynamic code execution.
- LLM cannot invent agent names; unknown names fail validation.
- Prefer system-managed definitions in Phase 8 (not user-editable freeform prompts).

---

## 6. Database model proposal

Migration when implemented: **`0009_multi_agent_orchestration`**.

### `AgentDefinition` (optional table or config-backed)

- `key` (stable), `name`, `description`, `version`
- `enabled`, `system_managed`
- `capabilities_json`, `allowed_tool_names_json`
- `maximum_steps`, `timeout_seconds`
- `created_at`, `updated_at`

Phase 8 may keep definitions code-registered and persist only runs/tasks if that reduces scope.

### `AgentRun`

- `id`, `user_id`, `conversation_id`
- `coordinator_agent`, `status`
- `original_request` (bounded), `safe_plan_summary`
- `started_at`, `completed_at`, `failed_at`, `duration_ms`
- `maximum_steps`, `steps_used`
- `correlation_id`
- `error_code`, `safe_error_message`
- `created_at`

Statuses: `pending`, `planning`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled`.

### `AgentTask`

- `id`, `agent_run_id`, `parent_task_id` (nullable)
- `assigned_agent`, `task_type`
- `safe_input_summary`, `status`, `sequence`, `depth`
- `started_at`, `completed_at`, `duration_ms`
- `retry_count`, `result_summary`, `error_code`
- `created_at`

### `AgentHandoff`

- `id`, `agent_run_id`, `from_agent`, `to_agent`
- `reason`, `safe_context_summary`, `created_at`

### `AgentApproval`

- `id`, `agent_run_id`, `task_id`, `user_id`
- `action_type`, `status`
- `safe_action_summary`
- `requested_at`, `resolved_at`, `resolution`
- Statuses: `pending`, `approved`, `rejected`, `expired`, `cancelled`

### `AgentRunEvent`

- `id`, `agent_run_id`, `task_id` (nullable)
- `event_type`, `agent_name`
- `safe_metadata_json`, `created_at`

All tables enforce `user_id` ownership; cross-user access returns safe 404.

---

## 7. Execution-state machine

### AgentRun

```
pending → planning → running ⇄ awaiting_approval → completed
                 ↘ failed
                 ↘ cancelled
```

Rules:

- Cancellation is idempotent and terminal.
- `awaiting_approval` pauses workers; no silent continuation.
- Completed/failed/cancelled tasks are not re-executed after restart.
- Persist state after every transition.

### AgentTask

```
queued → running → completed
                ↘ failed → (retry if policy allows) → failed_final
                ↘ cancelled
```

Default execution: **sequential** by `sequence` and dependency graph.  
Limited **parallel read-only** tasks only when the plan marks them safe and Safety Agent agrees.

Recursive re-planning requires an explicit remaining budget and a hard maximum (see limits).

---

## 8. Plan schema (provider-neutral)

```text
AgentPlan
  goal: str
  requires_multi_agent: bool
  reasoning_summary: str          # brief, user-safe; NOT private CoT
  tasks: list[AgentPlanTask]
  final_response_agent: str       # must be registered (usually conversation)

AgentPlanTask
  sequence: int
  agent_name: str                 # registry key
  task_type: str
  objective: str
  dependencies: list[int]
  allowed_tools: list[str]
  expected_output: str
  requires_approval: bool
  maximum_retries: int
```

Validation must reject:

- unknown agents / tools
- dependency cycles
- excessive depth or task count
- oversized input/output fields
- approval-required writes without `requires_approval=true` when Safety classifies them as sensitive

Never store or stream hidden chain-of-thought.

---

## 9. Context-governance rules

Each agent receives a filtered **context envelope**, not the full platform state.

### Allowed layers (selected, size-limited)

1. System policy for that agent  
2. Current user request  
3. Selected conversation history  
4. Selected approved memories  
5. Selected RAG passages  
6. Approved prior task outputs  
7. Approved tool results  
8. Run metadata (ids, budgets remaining)

### Never pass

- Full memory store or document collection  
- Unrelated conversation history  
- Secrets / raw credentials  
- Raw DB rows / internal IDs unless required  
- Hidden prompts or private CoT  
- Another agent’s unrestricted prompt  

### Budgets (config-driven defaults — illustrative)

| Budget | Suggested starting default |
|--------|----------------------------|
| Per-agent input characters | 12_000 |
| Task output characters | 4_000 |
| Total run context characters | 40_000 |
| Total LLM calls / run | 12 |
| Total tool calls / run | 8 |
| Total duration | 120s |
| Max plan tasks | 8 |
| Max delegation depth | 2 |
| Max coordinator steps | 12 |
| Max re-plan cycles | 1 |

---

## 10. Delegation limits

1. One coordinator per `AgentRun`.  
2. Agents registered server-side only.  
3. LLM cannot invent agent names.  
4. Delegation depth bounded (`max_depth`).  
5. Agent steps bounded (`maximum_steps`).  
6. Context filtered and size-limited.  
7. Ownership checks cannot be bypassed.  
8. Tool permissions cannot be bypassed.  
9. Writes require explicit user intent or approval.  
10. Every execution audited.  
11. Failures degrade safely to Conversation Agent or a safe error.  
12. Existing single-agent chat remains supported.  
13. Fake providers stay deterministic in tests.  
14. Native Ollama behavior must be verified in CI/manual matrix.  
15. Memory, RAG, tools, and history remain distinct layers.

---

## 11. Retry and timeout policies

- Per-task `timeout_seconds` from agent definition (hard cap from settings).  
- Per-task `maximum_retries` from plan, clamped by global max (e.g. 2).  
- Retry only for transient provider/tool failures — not policy/safety rejects.  
- Run-level wall clock timeout cancels remaining queued tasks.  
- On timeout: mark task failed, stream `agent_task_failed`, continue or stop per plan policy (`on_failure: stop|skip|degrade`).  
- Default for write tasks: **stop**; for optional read-only enrichment: **degrade**.

---

## 12. Approval model

`AgentApproval` gates sensitive actions. Phase 8 demonstrates infrastructure using existing safe actions (memory confirmations, settings changes) — **no external connectors**.

Requires approval examples:

- Saving/changing memory when policy requires confirmation  
- Deleting memory  
- Future write-capable tools  
- Persistent user settings changes  
- Any Safety Agent “sensitive” classification  

Coordinator must enter `awaiting_approval` and pause safely.  
UI resolves via approve/reject APIs. Expired approvals cannot be reused.

---

## 13. Safety model

- Unregistered agent/tool → hard fail.  
- Prompt injection in retrieved content must not alter system policy (Safety Agent + deterministic filters).  
- Sensitive context never streamed; secrets never logged.  
- Hidden reasoning never persisted.  
- Ownership enforced at repository layer, not only in prompts.  
- Fail closed on validation errors; fail open only for optional enrichment with explicit degrade path.

---

## 14. API proposal

All authenticated, user-owned, paginated where lists exist:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/agents` | List enabled registered agents (safe metadata) |
| GET | `/api/v1/agent-runs` | List own runs (status filters) |
| GET | `/api/v1/agent-runs/{run_id}` | Run detail |
| POST | `/api/v1/agent-runs/{run_id}/cancel` | Idempotent cancel |
| GET | `/api/v1/agent-runs/{run_id}/events` | Safe event timeline |
| GET | `/api/v1/agent-approvals` | Pending/resolved approvals |
| POST | `/api/v1/agent-approvals/{id}/approve` | Approve |
| POST | `/api/v1/agent-approvals/{id}/reject` | Reject |

Requirements: strict ownership, safe 404, no hidden prompts/reasoning, safe event metadata, approval ownership.

Chat streaming remains the primary UX path; these APIs support history, cancel, and approvals.

---

## 15. Streaming-event proposal

Backward-compatible additions (alongside existing tool/memory events):

- `agent_run_started`
- `agent_plan_created`
- `agent_plan_rejected`
- `agent_task_started`
- `agent_task_completed`
- `agent_task_failed`
- `agent_handoff`
- `agent_approval_required`
- `agent_approval_resolved`
- `agent_run_completed`
- `agent_run_failed`
- `agent_run_cancelled`

Never expose: hidden reasoning, raw prompts, secrets, full internal context, embeddings, stack traces.

---

## 16. Frontend proposal (design only — do not implement yet)

1. Agent activity strip in chat  
2. Expandable plan summary  
3. Task progress cards  
4. Handoff indicators  
5. Approval cards (approve/reject)  
6. `/agent-runs` history page  
7. Run details timeline  
8. Cancel action  
9. Safe error banners  
10. Phase 8 capability card **only after implementation** (do not retitle dashboard milestone during design)

Suggested labels:

- Planning request…  
- Searching your documents…  
- Checking approved memory…  
- Running calculator…  
- Preparing final response…  
- Approval required  
- Task completed  
- Agent run failed safely  

Do not show chain-of-thought.

---

## 17. Observability

- Structured logs with `correlation_id` / `agent_run_id` / `task_id`  
- Metrics: run duration, steps used, approval wait time, failure codes  
- Audit tables as source of truth for compliance-style review  
- Redact secrets in all log fields (reuse memory sanitizer patterns)

---

## 18. Test strategy (matrix)

### Architecture

- Registered agents only; duplicate registration rejected  
- Disabled agents unavailable  
- Invalid plans / cycles / excessive depth / excessive tasks rejected  

### Ownership

- Users see only own runs/approvals  
- Cross-user read/approve → safe 404  
- Anonymous rejected  

### Execution

- Simple request → Conversation Agent only (no AgentRun or empty plan)  
- Complex request → multi-agent with dependency order  
- Failed task stop/degrade per policy  
- Cancel, timeout, retry limit, max steps, call budget enforced  

### Safety

- Unregistered agent/tool blocked  
- Prompt injection in RAG/memory does not alter policy  
- Writes require approval when classified  
- Sensitive context not streamed; secrets not logged; no hidden reasoning persisted  

### Compatibility

- Normal chat, RAG, memory, tools, document mode, general mode  
- Native Ollama verified  
- Fake-provider tests deterministic  

### Persistence

- Run/approval/task state survives restart  
- Completed tasks not duplicated  
- Cancellation remains final  
- Audit events persist  

### Isolation

- Tests use `cortexa_agent_test` only  
- Two consecutive `make validate` runs preserve development data  

---

## 19. Migration plan

1. Add Alembic `0009_multi_agent_orchestration` (enums + tables + indexes + FKs).  
2. Register agents in lifespan alongside tools.  
3. Feature flag `MULTI_AGENT_ORCHESTRATION_ENABLED` (default false initially).  
4. Wire ChatService classifier → Coordinator path.  
5. Keep single-orchestrator fallback when flag off or plan says single-agent.  
6. Expand SSE + frontend progressively.  

Rollback: disable feature flag; runs remain readable historical records; chat falls back to Phase 6/7 orchestrator.

---

## 20. Incremental implementation order

1. Domain models + migration + repository  
2. AgentRegistry + stub agents (no LLM)  
3. Plan schema validation  
4. Coordinator sequential executor + audits + events  
5. Safety + approval pause  
6. ChatService integration behind flag  
7. Streaming + APIs  
8. Frontend activity + `/agent-runs`  
9. Ollama + fake-provider test matrix  
10. Docs + milestone update **only when complete**

Suggested commit structure when coding Phase 8:

1. `feat: add multi-agent run persistence`  
2. `feat: add agent registry and coordinator execution`  
3. `feat: integrate multi-agent orchestration into chat`  
4. `feat: add agent-run UI and approvals`  
5. `test: complete multi-agent safety and compatibility coverage`

---

## 21. Rollback strategy

- Feature flag off restores prior chat path immediately.  
- Do not delete `0009` data on rollback; keep historical runs.  
- If migration must be reverted in a broken environment, use a follow-up down migration only after backup — never casually on shared volumes.  
- Frontend should tolerate missing agent events (backward compatible).

---

## 22. Known limitations (Phase 8)

- No visual workflow builder  
- No dynamic agent creation by the LLM  
- No unlimited recursive planning  
- No background scheduled agents  
- Parallelism limited to safe read-only tasks  
- Approvals are synchronous pause (no email/Slack notification yet)  
- Agent definitions largely system-managed  

---

## 23. Explicit Phase 9 exclusions

Do **not** include in Phase 8:

- Gmail / Calendar / Slack / Teams connectors  
- External connectors generally  
- Background scheduled agents  
- Web browsing  
- Shell execution  
- Arbitrary SQL / Python / filesystem access  
- Remote MCP  
- Voice  
- Organization multi-tenancy  
- Visual workflow builder  
- Full workflow engine (Phase 9)  

---

## 24. Known risks

1. Classifier false positives creating unnecessary multi-agent runs (latency/cost).  
2. Over-retrieval of weakly related memories/documents into agent envelopes.  
3. Approval UX friction if too many gates fire.  
4. Ollama latency causing timeouts under multi-step runs.  
5. Plan schema drift across providers without strict validation.  
6. Accidental milestone/UI labeling before implementation is complete.

Mitigations: feature flag, conservative classifier defaults, budgets, fake-provider tests, explicit “Conversation-only” fallback, and keeping dashboard milestone unchanged until Phase 8 ships.
