# Development Standards

Coding and engineering standards for Cortexa AI Agent Platform.

These rules apply from Phase 1 onward when application code lands. Phase 0 establishes the contract.

---

## Core Principles

1. **Clean Architecture** — keep framework and IO at the edges.
2. **SOLID** — prefer small modules with clear responsibilities.
3. **Explicit over clever** — readable control flow beats abstraction theater.
4. **Honesty** — never ship fake business logic that pretends a feature works.
5. **Phase discipline** — do not implement future phases early.

---

## Backend (Python 3.12 / FastAPI)

### Structure

| Package | Allowed contents |
| --- | --- |
| `api/` | Routers, dependency wiring to services, HTTP mapping |
| `core/` | Settings, DI, logging, exceptions, security primitives |
| `schemas/` | Pydantic DTOs |
| `services/` | Business logic only |
| `repositories/` | Persistence access |
| `providers/` | External system adapters |
| `models/` | ORM / DB models |
| `db/` | Engine, sessions, migration hooks |
| `workers/` | Background jobs |
| `tests/` | Unit / integration tests |

### Rules

- Routes call **services** only (not repositories, providers, or ORM sessions).
- Services call **repositories** and **providers** via injected interfaces.
- **Never** call Ollama (or any external SDK) from API routes.
- **Never** run raw SQL from routes.
- Use type hints on public functions; prefer Pydantic models at boundaries.
- Avoid circular imports; keep provider protocols in stable modules.

### Style

- Formatter: Ruff format (or Black-compatible) — introduced with Phase 1 tooling
- Lint: Ruff
- Types: `mypy` or `pyright` in CI/local validation once tooling lands
- Tests: `pytest`

---

## Frontend (Node.js 22 / Next.js / TypeScript)

### Structure

| Directory | Allowed contents |
| --- | --- |
| `app/` | Routes, layouts, pages |
| `features/` | Domain-focused UI modules |
| `components/` | Shared presentational components |
| `hooks/` | React hooks |
| `stores/` | Client state |
| `services/` | Backend API clients |
| `lib/` | Pure utilities |
| `types/` | Shared TS types |
| `tests/` | Frontend tests |

### Rules

- TypeScript **strict** mode.
- Browser code talks to Cortexa backend only — never to Ollama directly.
- Prefer server/client component boundaries intentional under App Router.
- No fabricated dashboard metrics; empty states must be truthful.
- Keep styling consistent; avoid one-off design islands without shared tokens.

### Style

- ESLint + Prettier (or repo-standard equivalent) from Phase 2
- Test runner: Vitest / Playwright as introduced per phase needs

---

## Dependency Injection

- Construct concrete providers/repositories in composition root (`core` DI module).
- Pass interfaces into services.
- Tests substitute fakes/mocks at the composition boundary.

---

## Provider Pattern

Every external integration requires:

1. A protocol / interface in an internal module
2. A concrete provider implementation
3. Configuration via settings
4. Registration in DI

Examples of future providers: LLM, embeddings, vector store, speech, email (if ever), object storage.

---

## Repository Pattern

- One repository per aggregate/entity family unless complexity demands otherwise.
- Services orchestrate multiple repositories; repositories do not call services.
- Transactions are coordinated at the service or unit-of-work layer.

---

## Git & Commits

- Do not commit secrets or local `.env` files.
- Prefer small, phase-aligned commits when the operator requests commits.
- Commit messages explain **why**, not only what.
- Automation must not create commits unless explicitly requested.

---

## Documentation

- Update `docs/` when architecture boundaries or phase contracts change.
- README status line must reflect the active phase honestly.
- Do not document unimplemented endpoints as available.

---

## Validation Expectations (Per Phase)

At minimum, before requesting phase approval:

1. Relevant automated checks pass (Compose config, compile, lint, tests as applicable)
2. Manual smoke of new runtime surfaces
3. Confirm exclusions were not violated
4. Confirm no secrets added

---

## Naming

- Files/modules: `snake_case` (Python), `kebab-case` or feature folders (frontend) consistent with Next.js norms
- Classes: `PascalCase`
- Functions / variables: `snake_case` (Python), `camelCase` (TypeScript)
- Env vars: `SCREAMING_SNAKE_CASE` with domain prefixes (`CORTEXA_`, `POSTGRES_`, etc.)

---

## What Not To Do

- Do not put business rules in routers or React components.
- Do not create “TODO: implement later” stubs that expose fake successful agent responses.
- Do not add cloud SDKs “just in case” without a phase requirement.
- Do not weaken typing to ship faster.
