# Enterprise Administration Portal

The `/admin` workspace provides role-protected operational visibility and controls for the AI knowledge platform.

## Main areas

- dashboard and system health;
- users and access administration;
- knowledge/document visibility;
- conversations and memory administration;
- safe AI tools and execution history;
- RAG evaluations and exports;
- answer feedback review/resolution;
- enterprise AI analytics;
- durable background jobs and queue operations;
- audit history and safe platform settings.

## Administration principles

- normal users cannot access admin routes;
- destructive actions use explicit confirmation/guardrails where implemented;
- operational pages prefer bounded excerpts and metadata over exposing private content;
- global queue metrics remain admin-only;
- user-facing UUIDs are avoided where a human-readable selector is available.

See [SECURITY.md](SECURITY.md), [API_OVERVIEW.md](API_OVERVIEW.md), and [DEMO_GUIDE.md](DEMO_GUIDE.md).
