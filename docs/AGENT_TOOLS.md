# Safe AI Tools

Cortexa includes a typed tool framework for bounded server-side capabilities that can be invoked from supported AI workflows.

## Design

Each tool has a registered definition, validated input schema, explicit execution boundary and persisted audit/history metadata where applicable.

Examples include knowledge-search style utilities that reuse existing owner-scoped retrieval rather than bypassing document authorization.

## Safety rules

- tool definitions are allowlisted;
- inputs are validated before execution;
- tools do not receive unrestricted shell/database access;
- ownership checks are reused for knowledge operations;
- execution history is visible to the owning user/admin workflows;
- secrets and raw provider internals are not exposed through the UI.

The portfolio intentionally promotes the stable tool framework, not experimental autonomous multi-agent orchestration.
