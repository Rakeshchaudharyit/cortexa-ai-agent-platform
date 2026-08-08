# API Overview

Cortexa exposes versioned JSON APIs under `/api/v1` plus health/readiness endpoints and streaming conversation responses.

This is a route-family overview rather than an exhaustive OpenAPI copy. In development, the live FastAPI schema is available at `/docs`.

## Public/system endpoints

| Area | Representative paths | Purpose |
| --- | --- | --- |
| Health | `/health`, `/ready` | Liveness and dependency readiness |
| Auth | `/api/v1/auth/*` | Registration, login, refresh, logout, password reset |
| LLM status | `/api/v1/llm/status` | Provider/model diagnostics |

## User APIs

| Area | Representative paths | Purpose |
| --- | --- | --- |
| Documents | `/api/v1/documents` | Upload, list, metadata, archive/restore, versions, re-index |
| RAG | `/api/v1/rag/*` | Grounded retrieval and Q&A |
| Conversations | `/api/v1/conversations/*` | Persistent chat, messages, streaming, edit/regenerate |
| Memories | `/api/v1/memories/*` | User-controlled long-term memory |
| Tools | `/api/v1/tools/*` | Safe built-in tool access/execution history |
| Jobs | `/api/v1/jobs/*` | User-scoped durable job visibility/cancellation |

## Admin APIs

Admin routes require an authorized administrator role and include:

- dashboard and system health
- users
- documents
- conversations
- memories
- tools and tool executions
- analytics
- RAG evaluations and exports
- answer feedback review
- job operations
- audit history
- platform settings

## Streaming

Conversation generation uses Server-Sent Events over a fetch/ReadableStream client. The stream emits lifecycle metadata, content deltas, citations, and a final completion payload. Raw provider payloads and hidden reasoning are not forwarded to the browser.

## Error envelope

Controlled API failures use a request-correlated error shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": []
  },
  "request_id": "..."
}
```

## Authentication model

Access tokens are short-lived and held client-side in memory. Refresh sessions use HttpOnly cookies. Protected resources are resolved with ownership/role checks rather than trusting resource identifiers alone.

See [AUTHENTICATION.md](AUTHENTICATION.md) and [SECURITY.md](SECURITY.md).
