# Security Model

Cortexa is designed as a portfolio-quality enterprise AI knowledge platform with explicit authentication, authorization, ownership and privacy boundaries.

## Authentication and sessions

- short-lived bearer access tokens;
- HttpOnly refresh-session cookies;
- configurable secure/SameSite/domain policy;
- password hashing and bounded password policy;
- protected password-reset workflow.

## Authorization

- user-owned documents, conversations, citations, memories and jobs are resolved in authenticated scope;
- admin APIs require an administrator role;
- resource identifiers alone are never treated as authorization.

## Knowledge isolation

RAG retrieval is owner-scoped and only considers eligible active document versions. Archived/superseded/incomplete documents are excluded from normal retrieval.

## AI privacy

Operational analytics and quality workflows intentionally avoid persisting/exposing:

- hidden chain-of-thought/reasoning;
- system prompts;
- credentials or private keys;
- raw provider payloads;
- full retrieved passages in analytics dashboards.

Feedback/admin screens may show bounded answer excerpts and safe metadata required for review.

## Background processing

PostgreSQL is the durable job source of truth. Redis handles delivery. Worker execution uses independent database sessions, idempotency/retry controls, cancellation, stale-job recovery and dead-letter handling.

## File handling

Upload types and file sizes are bounded by configuration. PDF/DOCX extraction is content-oriented; scanned-image OCR is not part of the current platform.

## Development vs production

The included defaults are for local development. Public deployment requires:

- HTTPS;
- strong secrets and database credentials;
- secure cookies;
- restricted CORS;
- managed backups and restore testing;
- monitored database/Redis/worker health;
- durable document storage;
- production password-reset delivery;
- review of logs, retention and privacy requirements.

See [DEPLOYMENT.md](DEPLOYMENT.md) and [GITHUB_PUBLICATION_CHECKLIST.md](GITHUB_PUBLICATION_CHECKLIST.md).
