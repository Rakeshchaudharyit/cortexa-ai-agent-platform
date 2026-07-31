# Cortexa Agent Tools (Phase 6)

This document describes the Phase 6 agent-tool system: typed tool definitions,
registry, executor, orchestration loop, streaming events, persistence, APIs,
frontend visibility, and security controls.

## Architecture

```
ChatService
  └─ AgentOrchestrator (when AGENT_TOOLS_ENABLED)
       ├─ LLMService / LLMProvider (provider-neutral tool schemas + tool calls)
       ├─ ToolRegistry (server-side approved tools only)
       └─ ToolExecutor (auth → validate → timeout → persist → redact)
            └─ Built-in tools
```

Packages:

- `backend/app/tools/` — tool contract, registry, executor, builtins
- `backend/app/agents/` — orchestrator, prompts, policies, events
- `backend/app/models/tool_execution.py` — audit persistence
- `backend/app/api/routes/tools.py` — list tools / execution history

The tool system is **not** coupled to Ollama. Providers expose optional
`tools` / `tool_calls` on the shared LLM schemas. Ollama is adapted to that
interface.

## Tool contract

Each tool subclasses `BaseTool` with:

- `name`, `description`, `version`, `category`
- Pydantic `input_model` (arguments are never executed raw)
- optional `output_model`
- `required_roles`, `timeout_seconds`, `requires_confirmation`, `enabled`
- `expose_result_to_llm`
- `async execute(arguments, context) -> ToolResultPayload`

`ToolExecutionContext` carries only approved fields (user id/role, conversation /
message ids, DB session, correlation id, optional document scope, injectable
clock). It never receives raw HTTP requests, cookies, or tokens.

## Registry

`ToolRegistry` is an instance (created at app startup). It:

- registers / unregisters tools
- rejects duplicate and invalid names (`^[a-z][a-z0-9_]{1,62}$`)
- lists enabled tools deterministically
- filters by role
- emits provider-compatible `ToolSpec` JSON schemas

Tests create fresh registries; production uses `create_builtin_registry()`.

## Executor

`ToolExecutor` centralizes:

1. Lookup + enabled check
2. RBAC
3. Pydantic argument validation
4. Pending/running audit row
5. Timeout (`min(tool.timeout, AGENT_TOOL_TIMEOUT_SECONDS)`)
6. Execution
7. Redaction + result size limit
8. Success/failure persistence
9. Structured `ToolResultPayload` (no Python tracebacks to clients/LLM)

## Orchestration loop

When `AGENT_TOOLS_ENABLED=true` and an orchestrator is wired:

1. Load conversation + RAG context (existing Phase 5 behavior preserved)
2. Attach available tool schemas for the user role
3. Call the LLM provider
4. If tool calls are returned: validate → execute → append tool results → repeat
5. Stop on final text, max iterations, timeout, cancellation, or unrecoverable error

Default max iterations: `AGENT_MAX_TOOL_ITERATIONS=3`.

Recursive same-tool calls within one turn are rejected. Tool names and
arguments from the model are untrusted.

When tools are disabled, chat uses the previous text-only generate/stream path.

## Built-in tools

| Name | Purpose |
|------|---------|
| `calculator` | Safe AST arithmetic (`+ - * / % **`, parentheses). No `eval`. |
| `current_datetime` | IANA timezone clock with injectable `context.clock` for tests |
| `knowledge_search` | Adapter over Phase 4 `RetrievalService` (ownership preserved) |
| `conversation_summary` | Owner-scoped summary via LLM; non-recursive |

## Provider integration

Extended LLM types:

- `GenerateRequest.tools` / `tool_choice`
- `GenerateResponse.tool_calls`
- `ChatMessage` roles include `tool`; assistant messages may carry `tool_calls`

### Ollama tool-call support

The Ollama adapter sends `tools` on `/api/chat` and parses `message.tool_calls`
when present. **Native tool calling depends on the installed model.** Phase 6
does not claim live Ollama function calling works unless manually verified for
the active model (`OLLAMA_MODEL`). Deterministic tests use `FakeLLMProvider`
scripted turns.

## Streaming events

Backward-compatible events remain: `start`, `delta`, `citation`, `metadata`,
`complete`, `error`.

Added agent events:

- `agent_started`
- `tool_call_started`
- `tool_call_arguments`
- `tool_execution_started`
- `tool_execution_succeeded`
- `tool_execution_failed`
- `assistant_token`
- `assistant_completed`
- `agent_completed`
- `agent_failed`

Secrets, cookies, tokens, and stack traces are never streamed.

## Database model

Migration `0007_agent_tools` creates `tool_executions` with status enum:

`pending | running | succeeded | failed | denied | timed_out | cancelled`

Arguments/results are redacted and size-bounded. Ownership is by `user_id`.

## APIs

- `GET /api/v1/tools` — tools available to the current user
- `GET /api/v1/tool-executions` — owned history (paginated)
- `GET /api/v1/tool-executions/{id}` — owned detail
- `GET /api/v1/admin/tools` — admin list including disabled tools

There is **no** anonymous or arbitrary “run tool” endpoint. Execution happens
only through the orchestrator/executor policies.

Conversation detail responses include per-message `tool_executions` for refresh.

## Frontend

- Phase 6 platform overview on the home page (capability cards, agent tools section, quick actions)
- Chat composer modes: **General Agent** (`document_ids: []`, tools enabled) and **Document Knowledge** (RAG over owned docs)
- Live tool activity in chat via SSE (`ToolActivity` / `ToolExecutionCard`)
- Restored tool cards after reload from message `tool_executions`
- History page at `/tools`
- Friendly status text (“Using calculator…”, etc.)
- Expandable safe result JSON; no stack traces

**Note:** Document Knowledge with zero retrieval hits may stop before the agent loop. Use General Agent for tool calling.

## Security controls

- No eval/exec/shell/arbitrary SQL/HTTP/FS tools
- Server-side registry only
- Argument validation, timeouts, max result bytes, max iterations
- RBAC + ownership
- Secret redaction in logs/persistence
- Untrusted model tool names/arguments

## Adding a new tool

1. Create `backend/app/tools/builtins/my_tool.py` subclassing `BaseTool`
2. Register it in `create_builtin_tools()`
3. Add focused unit + orchestrator tests
4. Document the tool here
5. Do **not** add external SaaS OAuth integrations in this phase

## Testing strategy

- Isolated DB: `cortexa_agent_test` only
- FakeLLMProvider scripted tool turns for orchestration
- Calculator AST safety + no-eval checks
- API ownership/pagination/auth tests
- Frontend Vitest coverage for tool cards and streaming activity

## Configuration

```
AGENT_TOOLS_ENABLED=true
AGENT_MAX_TOOL_ITERATIONS=3
AGENT_TOOL_TIMEOUT_SECONDS=30
AGENT_MAX_RESULT_BYTES=32768
```

## Excluded from Phase 6 (historical)

The following remained out of Phase 6. Phase 7 later added long-term memory (see [LONG_TERM_MEMORY.md](LONG_TERM_MEMORY.md)); the rest remain excluded:

- Gmail / Google Calendar / Slack / Teams
- External web browsing
- Arbitrary shell / Python / SQL execution
- Remote MCP servers
- Third-party OAuth
- STT / TTS
- Organization-wide shared memory
- Autonomous background / scheduled agents

Built-in memory tools (`memory_list`, `memory_search`) added in Phase 7 are read-only and ownership-scoped.
