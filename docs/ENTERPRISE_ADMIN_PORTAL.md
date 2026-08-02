# Enterprise Administration Portal (Phase 8 / 8.1)

## Purpose

Cortexa’s enterprise SaaS admin portal gives authenticated **admin** users visibility and controlled management of users, documents, conversations, memories, tools, analytics, audit activity, system health, and safe platform settings.

Normal user APIs remain owner-scoped. Admin endpoints expose explicitly designed administrative views and audit every mutating action.

Phase 8.1 adds a dedicated administrator login experience and safe delete/deactivate workflows with impact previews, typed confirmation, cascading cleanup, and last-admin safeguards.

## Architecture

- **Backend package:** `backend/app/admin/` (schemas, repository, service, analytics, audit, settings, policies, deletion)
- **API routes:** `backend/app/api/routes/admin/*` under `/api/v1/admin/*`
- **Models / migration:** `PlatformSetting`, `ToolConfiguration`, `AdminAuditEvent` via `0009_enterprise_admin`; `tool_executions.user_id` nullable via `0010_admin_deletion_controls`
- **Frontend:** `/admin/*` App Router pages with `AdminGuard`, `AdminShell`, danger-zone/deletion dialogs
- **Charts:** `recharts` (dark-theme compatible line/area/bar charts)
- **Auth:** Reuses existing `POST /api/v1/auth/login`, HttpOnly refresh cookies, and `AuthProvider` — no second authentication system

## RBAC

Roles remain `user` and `admin` (`UserRole`).

All `/api/v1/admin/*` endpoints require:

1. authenticated access token
2. active account
3. `admin` role (`CurrentAdminUser` / `require_admin`)

Frontend route behavior:

| Route | Access |
|-------|--------|
| `/admin/login` | Public |
| `/admin/*` (other) | Active admin required |
| Unauthenticated `/admin/*` | Redirect to `/admin/login` |
| Authenticated non-admin | Safe access-denied (no portal content) |
| Authenticated admin on `/admin/login` | Redirect to `/admin` |
| Admin logout | Redirect to `/admin/login` |

Backend remains the source of truth.

## Creating an admin (development)

No admin is seeded automatically. Use the secure CLI:

```bash
docker compose exec backend python -m app.cli.create_user \
  --email admin@example.com \
  --name "Platform Administrator" \
  --role admin
```

Production is refused unless `ADMIN_USER_CLI_ALLOW_PRODUCTION=true`.

## Admin routes

| Path | Purpose |
|------|---------|
| `/admin/login` | Dedicated administrator login |
| `/admin` | Executive dashboard |
| `/admin/users` | User management |
| `/admin/users/[userId]` | User detail / deactivate / permanent delete |
| `/admin/documents` | Document administration / permanent delete |
| `/admin/conversations` | Archive / permanent delete |
| `/admin/memories` | Archive / delete and redact |
| `/admin/tools` | Tool configuration / reset override |
| `/admin/tool-executions` | Tool execution history (no casual delete) |
| `/admin/analytics` | Usage analytics (7/30/90d) |
| `/admin/audit` | Admin audit log (no delete) |
| `/admin/system` | System health |
| `/admin/settings` | Safe platform settings / reset to default |

## Deletion policy

| Entity | Policy |
|--------|--------|
| **Users** | Default: deactivate (revokes sessions). Permanent delete requires typed email confirmation; blocks self-delete and last active admin; cascades owned docs/conversations/memories/sessions; anonymizes tool executions (`user_id` null + redacted JSON); preserves audit with email fingerprint |
| **Documents** | Permanent delete removes row, chunks/embeddings, stored file; filename confirmation |
| **Conversations** | Archive (soft) or permanent delete (messages/citations cascade; memory source refs SET NULL) |
| **Memories** | Archive, reject, or delete/redact (content redacted, embedding cleared, excluded from retrieval) |
| **Tool executions** | No casual delete; retained/anonymized for governance |
| **Audit events** | No delete endpoint |
| **Tool configuration** | “Reset configuration” deletes DB override → registry default |
| **Platform settings** | “Reset to default” deletes safe DB override → env/default |

## Deletion impact previews

- `GET /api/v1/admin/users/{user_id}/deletion-impact`
- `GET /api/v1/admin/documents/{document_id}/deletion-impact`
- `GET /api/v1/admin/conversations/{conversation_id}/deletion-impact`
- `GET /api/v1/admin/memories/{memory_id}/deletion-impact`

Previews return counts and blocking reasons only — never private content, password hashes, or raw storage paths.

## API surface (Phase 8.1 additions)

- `POST /api/v1/admin/session/acknowledge` — audit successful admin portal session
- `POST /api/v1/admin/session/denied` — audit non-admin admin-login attempt
- `GET .../users/{id}/deletion-impact`, `DELETE /users/{id}`, `POST .../deactivate`, `POST .../activate`
- `GET .../documents/{id}/deletion-impact`, `DELETE /documents/{id}`
- `GET .../conversations/{id}/deletion-impact`, `POST .../archive`, `DELETE /conversations/{id}`
- `GET .../memories/{id}/deletion-impact` (+ existing archive/reject/delete)
- `DELETE /api/v1/admin/tools/{tool_name}/configuration`
- `DELETE /api/v1/admin/settings/{key}`

Existing Phase 8 list/detail/analytics/system endpoints remain.

## Data privacy

Admin lists minimize sensitive content:

- no password / refresh-token hashes
- no full private document text by default (optional audited excerpts)
- no conversation message bodies in list/detail metadata views
- no embeddings; deleted/rejected memory content redacted
- tool arguments/results redacted
- settings reject unsafe keys (JWT secret, DB URLs, etc.)
- deleted-user audits retain email fingerprint / safe identifiers only

## Tool configuration

`ToolConfiguration` persists enable/timeout/confirmation overrides validated against the server registry. The in-memory `ToolRegistry` applies overrides so disabled tools are unavailable to users. Reset removes the override row.

## Known limitations / Phase 9 exclusions

- No billing, OAuth, Gmail/Calendar, Slack/Teams
- No background agents / scheduled workflows / voice
- No org multi-tenancy beyond future foundation
- Token/cost analytics labeled unavailable when not tracked
- Read-mostly AI runtime config; only allowlisted DB overrides are editable
- Storage cleanup after DB commit is best-effort; failures are audited for operational follow-up
- No unrestricted table-purge or audit-log deletion

## Phase 9.3 agent administration APIs

Administrators can inspect safe agent definitions and run telemetry through
`GET /api/v1/admin/agents`, `GET /api/v1/admin/agents/{agent_key}`,
`GET /api/v1/admin/agent-runs`, and run detail. `PATCH /api/v1/admin/agents/{agent_key}`
only accepts bounded enablement, timeout, maximum-step, and tool-restriction changes.
Tool restrictions cannot expand the server allow-list, Coordinator and Safety cannot
be disabled, and every successful change is audited. Admin run responses redact the
user request and exclude prompts, passages, memory content, and provider payloads.
No admin agent frontend page is included in Phase 9.3.

## Testing

Backend: `backend/tests/test_admin_api.py`, `backend/tests/test_admin_deletion.py` (login events, impact, self/last-admin, deactivate, permanent delete + cleanup, authz).

Frontend: `frontend/tests/admin.test.tsx` (login page, guard, dashboard, deletion UX, reset labels).
