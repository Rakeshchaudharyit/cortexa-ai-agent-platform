# Enterprise Administration Portal (Phase 8)

## Purpose

Cortexa’s enterprise SaaS admin portal gives authenticated **admin** users visibility and controlled management of users, documents, conversations, memories, tools, analytics, audit activity, system health, and safe platform settings.

Normal user APIs remain owner-scoped. Admin endpoints expose explicitly designed administrative views and audit every mutating action.

## Architecture

- **Backend package:** `backend/app/admin/` (schemas, repository, service, analytics, audit, settings, policies)
- **API routes:** `backend/app/api/routes/admin/*` under `/api/v1/admin/*`
- **Models / migration:** `PlatformSetting`, `ToolConfiguration`, `AdminAuditEvent` via `0009_enterprise_admin`
- **Frontend:** `/admin/*` App Router pages with `AdminGuard`, `AdminShell`, reusable table/metric components
- **Charts:** `recharts` (dark-theme compatible line/area/bar charts)

## RBAC

Roles remain `user` and `admin` (`UserRole`).

All `/api/v1/admin/*` endpoints require:

1. authenticated access token
2. active account
3. `admin` role (`CurrentAdminUser` / `require_admin`)

Frontend `/admin/*` routes use `AdminGuard`:

- unauthenticated → login
- non-admin → access denied
- admin → portal shell

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
| `/admin` | Executive dashboard |
| `/admin/users` | User management |
| `/admin/users/[userId]` | User detail / actions |
| `/admin/documents` | Document administration |
| `/admin/conversations` | Conversation metadata |
| `/admin/memories` | Memory administration |
| `/admin/tools` | Tool configuration |
| `/admin/tool-executions` | Tool execution history |
| `/admin/analytics` | Usage analytics (7/30/90d) |
| `/admin/audit` | Admin audit log |
| `/admin/system` | System health |
| `/admin/settings` | Safe platform settings |

## API surface

- `GET /api/v1/admin/dashboard`
- `GET/PATCH /api/v1/admin/users/{id}`, `POST .../revoke-sessions`
- `GET/DELETE /api/v1/admin/documents/{id}`, `POST .../reprocess`
- `GET /api/v1/admin/conversations[/{id}]`
- `GET/DELETE /api/v1/admin/memories/{id}`, `POST .../archive|reject`
- `GET/PATCH /api/v1/admin/tools/{tool_name}`
- `GET /api/v1/admin/tool-executions[/{id}]`
- `GET /api/v1/admin/analytics?days=7|30|90`
- `GET /api/v1/admin/audit`
- `GET /api/v1/admin/system`
- `GET/PATCH /api/v1/admin/settings`

## Data privacy

Admin lists minimize sensitive content:

- no password / refresh-token hashes
- no full private document text by default (optional audited excerpts)
- no conversation message bodies in list/detail metadata views
- no embeddings; deleted/rejected memory content redacted
- tool arguments/results redacted
- settings reject unsafe keys (JWT secret, DB URLs, etc.)

## Tool configuration

`ToolConfiguration` persists enable/timeout/confirmation overrides validated against the server registry. The in-memory `ToolRegistry` applies overrides so disabled tools are unavailable to users.

## Known limitations / Phase 9 exclusions

- No billing, OAuth, Gmail/Calendar, Slack/Teams
- No background agents / scheduled workflows / voice
- No org multi-tenancy beyond future foundation
- Token/cost analytics labeled unavailable when not tracked
- Read-mostly AI runtime config; only allowlisted DB overrides are editable

## Testing

Backend: `backend/tests/test_admin_api.py` (authz, settings, last-admin protection, audit).

Frontend: `frontend/tests/admin.test.tsx` (guard, nav, dashboard, users, tools, system, settings, analytics).
