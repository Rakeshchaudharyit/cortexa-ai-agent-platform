# Cortexa Backend — Phase 4

See the repository root [README.md](../README.md) and [docs/RAG.md](../docs/RAG.md) for setup, document APIs, and RAG curl examples.

Phase 4 adds:

- Document upload / list / detail / delete
- Synchronous extract → chunk → embed pipeline
- pgvector retrieval and grounded `/api/v1/rag/query`
- Public `/api/v1/embeddings/status`

Pull the embedding model manually:

```bash
docker compose exec ollama ollama pull nomic-embed-text
```
