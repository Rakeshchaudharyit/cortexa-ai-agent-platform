# Portfolio Demo Guide

This walkthrough is designed for an Upwork portfolio review, GitHub reviewer, or technical client call. It focuses on implemented, stable functionality and can be completed in roughly five minutes.

## Prepare

1. Start the stack and verify all services are healthy.
2. Sign in with a clean demo user and an admin user.
3. Upload the documents under `demo/knowledge/`.
4. Allow background ingestion to reach `Ready`.
5. Create at least two evaluation cases: one answerable case and one safe no-answer case.

## Suggested walkthrough

### 1. Public product story — `/`

Explain that Cortexa is an enterprise RAG and AI quality platform, not a chatbot clone.

### 2. Knowledge Library — `/workspace`

Show:

- document folders and metadata;
- background ingestion progress;
- archive/restore;
- version history and active-version retrieval.

### 3. Grounded Chat — `/chat`

Use Document Knowledge mode and ask:

> How is Cortexa architected and how does it keep AI quality measurable?

Point out the streamed answer and document citations.

Then ask an unavailable-information question to demonstrate safe no-answer behavior.

### 4. Evaluations — `/admin/evaluations`

Show reusable RAG test cases and launch a background evaluation. Explain that changes to retrieval/model behavior can be measured against the same test set instead of judged manually.

### 5. AI Analytics — `/admin/analytics`

Show the AI Quality Score, knowledge health, success/reliability, latency, citations, feedback and evaluation trends.

### 6. Feedback Review — `/admin/feedback`

Show how users report low-quality answers and how an admin reviews, annotates and resolves the issue.

### 7. Background Operations — `/admin/jobs`

Show the worker heartbeat, document/evaluation jobs, progress, retries, cancellation, dead-letter state and requeue controls.

## Portfolio screenshots

Capture these seven screens with meaningful data:

1. public landing page;
2. grounded Chat with citations;
3. Knowledge Library with version/lifecycle badges;
4. RAG Evaluations;
5. Enterprise AI Analytics;
6. Feedback Review;
7. Background Jobs operations console.

Avoid screenshots containing empty states, raw UUIDs, browser developer tools, localhost error banners, or historical experimental agent pages.
