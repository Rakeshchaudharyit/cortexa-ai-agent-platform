# Cortexa Security & Access Policy

Protected application areas require authentication. Administrative APIs and screens require administrator authorization. Refresh tokens are kept in HttpOnly cookies and access tokens are short-lived.

Documents, conversations, memories, and knowledge retrieval are scoped to the authenticated owner unless an authorized administrative workflow explicitly requires broader access. Archived and superseded document versions are excluded from active retrieval unless restored or made active.

Operational telemetry avoids system prompts, hidden reasoning, credentials, full retrieved passages, and raw provider payloads. Feedback review uses bounded answer excerpts and safe operational metadata.
