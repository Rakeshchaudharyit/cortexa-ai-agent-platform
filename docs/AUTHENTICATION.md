# Authentication (Phase 3)

Cortexa authentication foundation: email/password users, short-lived JWT access tokens, opaque refresh tokens in HttpOnly cookies, and refresh-token rotation.

## Architecture

```text
Browser
  ├─ access token (memory only)
  └─ refresh cookie (HttpOnly) ──► POST /api/v1/auth/refresh
Backend
  ├─ AuthService (register/login/refresh/logout)
  ├─ PasswordService (Argon2id)
  ├─ TokenService (HS256 JWT access tokens)
  └─ PostgreSQL users + refresh_sessions
```

## Token lifecycle

1. **Register / login** — creates an active user session, returns `access_token` in JSON, sets `cortexa_refresh` HttpOnly cookie.
2. **API calls** — `Authorization: Bearer <access_token>`.
3. **Refresh** — browser calls `POST /api/v1/auth/refresh` with credentials; server rotates the refresh session and returns a new access token.
4. **Reuse detection** — presenting an already-rotated refresh token revokes the entire token family.
5. **Logout** — revokes the current refresh session and clears the cookie.

Access tokens are never stored in `localStorage` or `sessionStorage`. Refresh tokens are never returned to JavaScript.

## Cookie security

| Setting | Default (dev) | Notes |
| --- | --- | --- |
| Name | `cortexa_refresh` | `AUTH_COOKIE_NAME` |
| HttpOnly | `true` | Always |
| Secure | `false` | Set `AUTH_COOKIE_SECURE=true` in production |
| SameSite | `lax` | `AUTH_COOKIE_SAMESITE` |
| Path | `/api/v1/auth` | Limits cookie scope |
| Domain | unset | Optional `AUTH_COOKIE_DOMAIN` |

CORS uses explicit origins with `allow_credentials=True`. Wildcard origins are not used.

## Route protection

| Endpoint | Auth |
| --- | --- |
| `GET /health`, `GET /ready` | Public |
| `GET /api/v1/system/info` | Public |
| `GET /api/v1/llm/status` | Public |
| `POST /api/v1/auth/*` (except `/me`) | Public (credentialed) |
| `GET /api/v1/auth/me` | Bearer access token |
| `POST /api/v1/llm/generate` | Bearer + active user |
| `POST /api/v1/llm/stream` | Bearer + active user |

Disabled accounts cannot log in, refresh, or use access tokens.

## Password policy

- Argon2id hashing (`argon2-cffi`)
- Minimum length: `PASSWORD_MIN_LENGTH` (default 12)
- Maximum length: `PASSWORD_MAX_LENGTH` (default 128)
- Passphrases allowed; blank passwords rejected
- Passwords are never logged or returned

## curl examples

Replace host/port if your `.env` remaps ports (for example `18000`).

### Register

```bash
curl -i \
  -c /tmp/cortexa-cookies.txt \
  -X POST http://localhost:18000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "StrongDemoPassword123!",
    "full_name": "Demo User"
  }'
```

Successful response includes `user`, `access_token`, `token_type`, `expires_in`, and `access_token_expires_at`, plus a `Set-Cookie` for the refresh token.

### Login

```bash
curl -i \
  -c /tmp/cortexa-cookies.txt \
  -X POST http://localhost:18000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "StrongDemoPassword123!"
  }'
```

### Current user

```bash
ACCESS_TOKEN='…paste access_token…'
curl -i \
  http://localhost:18000/api/v1/auth/me \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

### Refresh

```bash
curl -i \
  -b /tmp/cortexa-cookies.txt \
  -c /tmp/cortexa-cookies.txt \
  -X POST http://localhost:18000/api/v1/auth/refresh
```

### Logout

```bash
curl -i \
  -b /tmp/cortexa-cookies.txt \
  -X POST http://localhost:18000/api/v1/auth/logout
```

### Protected LLM generate

```bash
curl -i \
  -X POST http://localhost:18000/api/v1/llm/generate \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Protected LLM stream

```bash
curl -N -i \
  -X POST http://localhost:18000/api/v1/llm/stream \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Production hardening (required later)

- Replace `JWT_SECRET_KEY` with a unique high-entropy secret
- Enable `AUTH_COOKIE_SECURE=true` behind HTTPS
- Rate-limit `/auth/login`, `/auth/register`, and `/auth/refresh` (structure is ready; limiter not shipped in Phase 3)
- Do not log passwords, raw tokens, or `Authorization` / `Cookie` headers (access logs already redact these)

## Security limitations (Phase 3)

- No email verification delivery
- No password-reset email flow
- No social login
- No organization / tenant model
- No admin dashboard (role enum exists only)
- No API-key authentication
- Rate limiting is documented but not enforced yet
