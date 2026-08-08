# Phase 10.3 — User Feedback and Answer Review

Phase 10.3 adds a privacy-aware feedback loop to the stable Chat/RAG product.

## User experience

- Helpful and Not helpful controls on completed assistant responses.
- Structured issue reasons: incorrect, missing source, not relevant, incomplete, unclear, or other.
- Optional bounded comment.
- Feedback can be updated or removed and persists after refresh.

## Admin review

`/admin/feedback` provides a review queue with sentiment, issue reason, bounded answer excerpt, model/provider metadata, grounding state, user comment, and workflow states: open, reviewed, resolved.

## Privacy

The review API does not expose user questions, retrieved passages, hidden reasoning, system prompts, credentials, or raw provider payloads. Only a bounded assistant-answer excerpt and operational metadata are returned.
