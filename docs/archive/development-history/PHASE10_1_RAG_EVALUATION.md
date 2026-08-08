# Phase 10.1 — RAG Evaluation Framework

Phase 10.1 adds repeatable, admin-controlled quality measurement for grounded document answers.

## Capabilities

- Admin CRUD for evaluation cases linked to a specific user's private knowledge base.
- Positive cases (`should_answer=true`) and no-answer safety cases.
- Optional expected keywords and expected document citations.
- Bounded synchronous evaluation runs with immutable per-case results.
- Deterministic metrics: groundedness, keyword recall, citation match, answerability, and composite score.
- Run history with provider, model, latency, pass/fail counts, and average score.
- No hidden reasoning, full prompts, document passages, or secrets are persisted in evaluation results.

## Scoring

Composite score:

- Groundedness: 35%
- Expected keyword recall: 30%
- Expected citation match: 20%
- Answerability/no-answer correctness: 15%

A case passes at 0.75 or higher.

## Limitations

This milestone intentionally uses deterministic evaluators. LLM-as-judge evaluation may be added later only as an optional, separately auditable metric.
