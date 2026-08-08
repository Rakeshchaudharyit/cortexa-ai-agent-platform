# Portfolio Launch 2 — Public Landing + Demo Data

## Purpose

Make the repository immediately understandable to an Upwork/GitHub reviewer before authentication.

## Public routes

- `/` — public product landing page
- `/demo` — guided product tour based only on implemented capabilities
- `/workspace` — existing authenticated product overview and Knowledge Library

Authentication redirects now land on `/workspace`.

## Demo knowledge

The repository contains a curated, non-sensitive demo pack under `demo/knowledge/`:

- Cortexa_Platform_Architecture.md
- Cortexa_Deployment_Operations.md
- Cortexa_Security_Access_Policy.md
- Cortexa_AI_Quality_Governance.md

These files are intentionally about the product itself, so they are safe for screenshots and repeatable portfolio demonstrations.

## Recommended live demo sequence

1. Sign in to the workspace.
2. Create folders: Architecture, Operations, Security, Quality.
3. Upload the four bundled demo documents.
4. Wait for background ingestion to reach Ready.
5. Ask in Document Knowledge mode: `How is Cortexa architected and how does it keep AI quality measurable?`
6. Show citations.
7. Run one RAG evaluation.
8. Submit feedback on an answer and show Admin Feedback Review.
9. Open Enterprise Analytics.
10. Open Background Jobs to show durable execution.

No synthetic operational metrics are added by Portfolio Launch 2.
