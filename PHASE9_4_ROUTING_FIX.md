# Phase 9.4 routing fix

## Root cause

The complex browser request was submitted while the composer was still in **General Agent** mode. General mode intentionally sends `document_ids: []`, which disables document retrieval. Without document context, the classifier saw only a calculator operation plus response synthesis, so it correctly kept the request on the single-agent path and no `AgentRun` row was created.

The ad-hoc `app.state.multi_agent_service` check failed because importing `app.main.app` in a standalone Python process does not enter FastAPI's lifespan. The service is initialized during the running application's lifespan; this was not the runtime defect.

## Fix

The composer now detects explicit document references such as “selected document”, “uploaded file”, “attached contract”, or “this report”. When ready documents are available and the composer is still in General Agent mode, sending such a request automatically routes it through Document Knowledge (`document_ids: null`, meaning all authorized ready documents) and updates the visible composer mode.

Ordinary requests continue to send `document_ids: []` and stay on the fast single-agent path.

## Validation

Run locally:

```bash
make validate
make validate
docker compose up -d --build frontend backend
```

Manual checks:

1. In General Agent mode, send `Explain FastAPI in two sentences.` — no Agent Run should be created.
2. In General Agent mode with at least one ready document, send:
   `Review the selected document, identify the main risks, calculate a 15 percent contingency, and prepare a concise recommendation.`
3. The composer should switch to Document Knowledge, the backend should create an Agent Run, and `/agent-runs` should show it.
