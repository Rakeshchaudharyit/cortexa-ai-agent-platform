# Architecture Diagrams

These Mermaid diagrams render directly on GitHub and are intended for technical reviewers and portfolio walkthroughs.

## 1. System context

```mermaid
flowchart LR
    User[Knowledge User] --> Web[Cortexa Web App]
    Admin[Administrator] --> Web
    Web --> API[FastAPI API]
    API --> DB[(PostgreSQL + pgvector)]
    API --> Redis[(Redis)]
    Redis --> Worker[Background Worker]
    API --> LLM[LLM / Embedding Provider]
    Worker --> LLM
    API --> Files[(Document Storage)]
    Worker --> Files
```

## 2. Grounded RAG request

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Next.js
    participant API as FastAPI
    participant DB as PostgreSQL/pgvector
    participant LLM as LLM Provider

    U->>UI: Ask in Document Knowledge mode
    UI->>API: Stream conversation message
    API->>DB: Retrieve owner-scoped active chunks
    DB-->>API: Ranked passages + metadata
    API->>API: Deduplicate + context-budget passages
    API->>LLM: Grounded prompt with selected context
    LLM-->>API: Stream answer
    API->>API: Validate citation markers
    API->>DB: Persist message + citation snapshots + timing
    API-->>UI: SSE deltas, citations, complete
```

## 3. Background document ingestion

```mermaid
sequenceDiagram
    participant UI as Browser
    participant API as FastAPI
    participant DB as PostgreSQL
    participant R as Redis
    participant W as Worker
    participant AI as Embedding Provider

    UI->>API: Upload document
    API->>DB: Create document + durable job
    API->>R: Publish job ID
    API-->>UI: Accepted / queued
    R-->>W: Deliver job
    W->>DB: Claim durable job
    W->>W: Extract + chunk
    W->>AI: Generate embeddings
    AI-->>W: Vectors
    W->>DB: Atomic index finalization + activate version
    W->>DB: Mark job succeeded
    UI->>API: Poll document/job progress
```

## 4. Knowledge version lifecycle

```mermaid
stateDiagram-v2
    [*] --> Processing
    Processing --> Active: indexing succeeds
    Processing --> Failed: indexing fails
    Active --> Superseded: newer version activates
    Active --> Archived: archive
    Archived --> Active: restore
    Superseded --> Active: make historical version active
    Failed --> Processing: requeue/re-index
```

Only the active, ready, non-archived version is eligible for normal RAG retrieval.

## 5. AI quality feedback loop

```mermaid
flowchart LR
    Chat[Production RAG Answers] --> Metrics[Latency / Retrieval / Citations]
    Chat --> Feedback[Helpful / Not helpful]
    EvalCases[Evaluation Cases] --> EvalRun[Background Evaluation]
    EvalRun --> EvalResults[Groundedness / Recall / Citation / Pass Rate]
    Feedback --> Review[Admin Review & Resolution]
    Metrics --> Analytics[Enterprise AI Analytics]
    EvalResults --> Analytics
    Review --> Analytics
```

## 6. Durable job state

```mermaid
stateDiagram-v2
    [*] --> queued
    queued --> running
    running --> succeeded
    running --> retrying: transient failure
    retrying --> queued: retry due
    running --> cancelled: cancellation observed
    running --> dead_lettered: attempts exhausted
    retrying --> dead_lettered: attempts exhausted
    dead_lettered --> queued: admin requeue
```
