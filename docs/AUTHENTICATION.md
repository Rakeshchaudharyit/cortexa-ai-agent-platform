# Authentication

Cortexa uses short-lived bearer access tokens with refresh sessions stored in HttpOnly cookies.

## Browser flow

1. User registers or signs in.
2. API returns an access token and sets the refresh cookie.
3. The frontend keeps the access token in memory rather than `localStorage`.
4. On reload/expiry, the browser calls the refresh endpoint with `credentials: include`.
5. Logout/revocation invalidates the refresh session.

## Security characteristics

- Argon2-based password hashing through the backend security layer.
- Configurable password length limits.
- Short-lived access tokens and longer-lived refresh sessions.
- HttpOnly refresh cookie with configurable Secure, SameSite, domain and path values.
- Protected routes resolve the authenticated user before owner/admin authorization.
- Admin routes require an administrator role.
- Password-reset tokens are bounded, expiring, and delivery-provider controlled.

## Local hostname rule

For local browser testing, keep the frontend and API on the same loopback hostname family. For example:

```text
http://localhost:13000
http://localhost:18000
```

Do not mix `localhost` and `127.0.0.1` in the same refresh-cookie flow unless cookie policy is intentionally configured for it.

## Production configuration

Before deployment:

- generate a strong `JWT_SECRET_KEY`;
- set `AUTH_COOKIE_SECURE=true` behind HTTPS;
- restrict CORS to deployed origins;
- configure the intended cookie domain/SameSite policy;
- disable development password-reset notices/token exposure;
- use a real password-reset delivery provider if password reset is exposed publicly.

See `.env.example`, [SECURITY.md](SECURITY.md), and [DEPLOYMENT.md](DEPLOYMENT.md).
