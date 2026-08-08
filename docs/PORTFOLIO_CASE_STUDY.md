# Portfolio Case Study

## Cortexa AI Knowledge Platform

**Enterprise RAG · Knowledge Management · AI Quality Operations**

### The engineering problem

A useful enterprise knowledge assistant needs more than retrieval and a chat box. Production systems must control document lifecycle, preserve tenant/user boundaries, handle slow AI workloads outside web requests, measure answer quality, surface operational health, and provide a human review path when AI responses are wrong or incomplete.

### The solution

Cortexa brings those concerns into one production-oriented platform:

- private document ingestion and pgvector retrieval;
- grounded multi-turn chat with persisted citation snapshots;
- document folders, active versions, archive/restore and lifecycle history;
- automated RAG evaluation and quality scoring;
- Helpful / Not helpful feedback with admin resolution workflows;
- enterprise analytics for quality, latency, citations, reliability and knowledge health;
- Redis-delivered, PostgreSQL-durable background jobs for ingestion, re-indexing, evaluation and export;
- role-based administration, auditability and secure operational controls.

### Key architectural decisions

**PostgreSQL as the source of truth for jobs.** Redis handles delivery, while job state, progress, attempts and results remain durable in PostgreSQL.

**Active-version retrieval.** Historical document versions remain available for governance, but normal RAG uses only the active, ready, non-archived version.

**Quality as a first-class workflow.** Evaluation runs, user feedback and analytics are not afterthoughts; they create a measurable improvement loop.

**Long-running workloads outside request lifecycles.** Embedding/indexing and evaluation work runs in a dedicated worker rather than blocking API requests.

**Privacy-aware observability.** Analytics uses operational metadata rather than exposing hidden reasoning, credentials or full private document passages.

### Stack

FastAPI · Python · Pydantic · SQLAlchemy · Alembic · PostgreSQL · pgvector · Redis · Next.js · React · TypeScript · Tailwind CSS · Docker Compose · Ollama

### What this project demonstrates

- production RAG engineering;
- FastAPI backend architecture;
- asynchronous/durable job processing;
- vector retrieval and citation systems;
- AI evaluation and observability;
- enterprise administration and RBAC;
- document governance/versioning;
- full-stack TypeScript/Python delivery;
- operational debugging and resilience improvements.

### Suggested Upwork portfolio title

**Enterprise AI Knowledge Platform | RAG, FastAPI, pgvector & AI Quality**

### Suggested short description

Built a production-oriented AI knowledge platform using FastAPI, Next.js, PostgreSQL/pgvector and Redis. The system includes grounded document chat with citations, knowledge lifecycle/versioning, automated RAG evaluation, human feedback review, enterprise AI analytics, and durable background processing with retries, cancellation and dead-letter recovery.
