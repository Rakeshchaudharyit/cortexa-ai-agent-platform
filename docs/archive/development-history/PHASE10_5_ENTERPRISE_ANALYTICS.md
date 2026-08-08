# Phase 10.5 — Enterprise AI Analytics & Quality Dashboard

Phase 10.5 upgrades the existing content-free observability screen into an enterprise quality and knowledge-health dashboard.

## AI quality score

The score is a transparent operational indicator composed from available data:

- latest completed RAG evaluation score (35%)
- helpful user-feedback rate (25%)
- successful assistant-response rate (20%)
- citation coverage across RAG responses (20%)

Unavailable components are excluded and the remaining weights are normalized. The score is not presented as proof of factual correctness.

## Knowledge health

The dashboard reports total, ready, pending, processing and failed documents, plus documents with zero chunks, documents not updated for more than 90 days, and duplicate checksum groups. A bounded health score highlights collections that require attention.

## Enterprise breakdowns

- most-used knowledge documents based on persisted citations
- model usage based on completed assistant messages
- evaluation score and pass-rate trend
- feedback totals and open review workload
- request outcomes and daily latency

## Privacy

The analytics endpoint never returns prompts, answers, document passages, memory content, tool arguments, credentials, provider payloads or hidden reasoning.

## Database impact

No migration is required. The phase derives metrics from existing messages, citations, documents, evaluation runs and feedback records.
