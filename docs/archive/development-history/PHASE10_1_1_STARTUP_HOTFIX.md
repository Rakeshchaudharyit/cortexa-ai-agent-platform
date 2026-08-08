# Phase 10.1.1 — FastAPI 204 Startup Hotfix

## Issue

The backend failed during application import because the evaluation-case DELETE route declared HTTP 204 without an explicit empty response class. FastAPI rejects 204 routes that may generate a response body.

## Resolution

- The route now uses `response_class=Response`.
- The handler explicitly returns `Response(status_code=204)`.
- Added a regression test that validates the route's 204 response contract.

No database migration changes are required.
