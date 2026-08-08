# Cortexa AI Knowledge Platform — Architecture

Cortexa uses a Next.js and TypeScript frontend with a FastAPI and Python backend. PostgreSQL is the durable relational database and pgvector stores document embeddings for semantic retrieval. Redis provides queue delivery for durable background jobs. Ollama is supported for local LLM generation and embedding workloads.

The platform separates browser experience, typed API routes, application services, database persistence, queue transport, retrieval, and model-provider integrations. Docker Compose runs the local application stack.

Core product workflows include grounded RAG chat with citations, governed document lifecycle and versioning, RAG evaluations, feedback review, enterprise analytics, and background document ingestion.
