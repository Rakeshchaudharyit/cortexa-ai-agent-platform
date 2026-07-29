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
- **Passwords are never trimmed** — leading/trailing whitespace is significant
- Emails are trimmed and lowercased via shared `normalize_email`
- Passwords are never logged or returned
- Registration requires `confirm_password` matching `password`

## Password reset (Phase 5.1)

Secure, enumeration-safe password recovery:

1. `POST /api/v1/auth/forgot-password` — always returns the same message whether or not the email exists
2. Development delivery stores the reset link in Redis (no real email; never PostgreSQL)
3. Retrieve the link with the development CLI (deletes the Redis value after retrieval)
4. `POST /api/v1/auth/reset-password` — single-use, expiring token; updates Argon2 hash; revokes all refresh sessions and other reset tokens
5. User must log in again with the new password (no auto-login)

### Reset token security

- Raw token: `secrets.token_urlsafe(PASSWORD_RESET_TOKEN_BYTES)` (default 32 bytes)
- Stored only as SHA-256 hex digest
- Expiry: `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` (default 30)
- Max active tokens per user: `PASSWORD_RESET_MAX_ACTIVE_TOKENS` (default 3)
- Cooldown: Redis key on email-hash + IP-hash (`PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS`); fail-open if Redis is down
- Invalid / expired / used / revoked tokens share: “This password reset link is invalid or has expired.”

### Development reset-link workflow

After calling forgot-password (API or UI), retrieve the link:

```bash
docker compose exec backend \
  python -m app.cli.get_password_reset_link \
  --email user@example.com
```

Refuses to run when `APP_ENV=production`. Prints only the reset URL (never the password). Deletes the Redis delivery value after retrieval so a second CLI call returns no link.

Development delivery Redis policy:

- Key: `cortexa:pwd_reset:dev_delivery:` + HMAC-SHA256(normalized email) — no plaintext email in the key
- Value: raw reset URL only (never stored in PostgreSQL)
- TTL: `PASSWORD_RESET_TOKEN_EXPIRE_MINUTES` (seconds)
### Secure admin password CLI

```bash
docker compose exec backend \
  python -m app.cli.reset_password \
  --email user@example.com
```

Prompts twice via `getpass`. Never accepts the password as a CLI argument. Revokes refresh sessions and active reset tokens.

### Frontend routes

| Path | Purpose |
| --- | --- |
| `/forgot-password` | Request reset (generic success) |
| `/reset-password?token=…` | Set new password; token removed from URL after success |

Reset tokens are never written to `localStorage` / `sessionStorage`.

### Production email limitation

`PASSWORD_RESET_DELIVERY_PROVIDER=development` is the only provider in Phase 5.1. Real SMTP / transactional email is a later deployment task. `PASSWORD_RESET_DEV_EXPOSE_TOKEN` must remain `false` in production.

## Troubleshooting login after registration

1. Confirm register returned **201** and `/auth/me` works with the access token.
2. Log out, then login with the **exact** same password (no trimming; use Show password).
3. Confirm email casing/whitespace — backend normalizes both register and login.
4. If you mistyped at registration, use forgot-password or the admin CLI.
5. Stale refresh cookies do not block password login; a successful login replaces the cookie.
6. Network / 500 errors must not be shown as “Invalid email or password”.

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
    "confirm_password": "StrongDemoPassword123!",
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

### Forgot password

```bash
curl -i \
  -X POST http://localhost:18000/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "demo@example.com"}'
```

### Reset password

```bash
# Obtain TOKEN via: docker compose exec backend python -m app.cli.get_password_reset_link --email demo@example.com
curl -i \
  -X POST http://localhost:18000/api/v1/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{
    "token": "TOKEN",
    "new_password": "BrandNewSecurePass456!",
    "confirm_password": "BrandNewSecurePass456!"
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
- Wire a real email provider for password-reset delivery
- Rate-limit `/auth/login`, `/auth/register`, and `/auth/refresh` (forgot-password has lightweight Redis cooldown)
- Do not log passwords, raw tokens, or `Authorization` / `Cookie` headers (access logs already redact these)

## Security limitations (Phase 5.1)

- No email verification delivery
- Password-reset delivery is development-only (no SMTP yet)
- No social login
- No organization / tenant model
- No admin dashboard (role enum exists only)
- No API-key authentication
- Login/register/refresh rate limiting is documented but not fully enforced yet
