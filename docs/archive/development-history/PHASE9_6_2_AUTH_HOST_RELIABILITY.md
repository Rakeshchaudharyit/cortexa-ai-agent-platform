# Phase 9.6.2 — Authentication Host Reliability

## Problem

The frontend was commonly opened at `http://localhost:13000`, while the browser
API base URL was configured as `http://127.0.0.1:18000`. Browsers treat these as
different sites. The in-memory access token allowed the initial session to work,
but after a hard refresh the `SameSite=Lax` HttpOnly refresh cookie was not sent
to the other loopback hostname, causing protected Agent Run routes to redirect to
login.

## Fix

- Align loopback API requests with the hostname used to open the frontend.
- Preserve the configured API scheme and port.
- Rewrite only `localhost`, `127.0.0.1`, and `::1`; production hosts are never changed.
- Keep access tokens in memory and refresh tokens in secure HttpOnly cookies.
- Change local defaults to `localhost` for a consistent developer experience.
- Add focused unit tests for hostname alignment.

## Security

The fix does not weaken cookie attributes, persist access tokens in browser
storage, or allow arbitrary API-host rewriting. It only normalizes equivalent
loopback hosts during local development.
