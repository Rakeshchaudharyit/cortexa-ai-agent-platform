# Product Roadmap

Cortexa's current portfolio release already includes grounded RAG, knowledge lifecycle/versioning, AI quality evaluation, feedback review, analytics, and durable background operations.

Future work should be driven by real deployment or client requirements rather than adding portfolio features indefinitely.

## Candidate future directions

### Enterprise source connectors

A provider-neutral connector framework for sources such as Google Drive, Notion, Confluence, SharePoint or S3, with incremental sync and source attribution.

### Production observability

OpenTelemetry traces, centralized metrics/logs, alerting, deployment dashboards, backup/restore automation, and load/resilience testing.

### Scalable provider deployment

Managed LLM/embedding providers, provider routing, independently scalable worker pools, and production object storage.

### Durable advanced orchestration

If multi-agent workflows are reintroduced, they should execute as durable worker-owned runs with independent database sessions and reconnect-safe persisted events rather than request-bound orchestration.

## Portfolio policy

New capabilities should be added only when they materially strengthen a real client use case, production deployment, or reusable engineering pattern.
