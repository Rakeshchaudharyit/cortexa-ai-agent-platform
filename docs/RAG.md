# RAG & Documents (Phase 4)

Cortexa Phase 4 adds private document ingestion, local embeddings (Ollama `nomic-embed-text`), pgvector storage, and grounded retrieval-augmented answers with citations.

## Capabilities

| Capability | Behavior |
| --- | --- |
| Upload | Multipart `POST /api/v1/documents` — **synchronous** ingest in the request |
| Formats | `.txt`, `.md`, `.pdf`, `.docx` |
| Size limit | 5 MiB (`DOCUMENT_MAX_FILE_SIZE_BYTES`) |
| Ownership | Documents and chunks are scoped to the authenticated user |
| Duplicates | Same SHA-256 checksum per user → `409 duplicate_document` |
| Embeddings | Ollama embedding model (default `nomic-embed-text`, 768-dim) |
| Retrieval | pgvector cosine similarity + `RAG_MIN_SIMILARITY` threshold |
| RAG | `POST /api/v1/rag/query` — grounded answer + citation cards; no LLM call when no context |
| Status | Public `GET /api/v1/embeddings/status` (does not gate `/ready`) |

## Supported formats & limits

- **Allowed extensions:** `.txt`, `.md`, `.pdf`, `.docx`
- **Max upload size:** 5 MiB
- **PDF:** text extraction only (no OCR); encrypted PDFs are rejected
- **DOCX:** paragraphs and tables; macros/embedded objects ignored
- **Empty extracts** fail with `empty_document`
- Chunking is deterministic (character/paragraph based with overlap)

## Sync ingestion

Upload validates → stores bytes under `DOCUMENT_STORAGE_PATH` → extracts text → chunks → embeds → writes `document_chunks` → marks the document `ready` (or `failed`). There is no async worker in Phase 4.

## Duplicate rejection

Per-user uniqueness on `checksum_sha256`. Re-uploading the identical file for the same account returns `409`.

## Ownership & isolation

List/detail/delete/RAG retrieval only see the caller’s documents. Filtering RAG by another user’s `document_id` returns `404 document_not_found`.

## Citation behavior

When retrieval returns chunks, the LLM is prompted to answer only from context and cite with markers like `[1]`. The API returns structured `citations` (`citation_id`, filename, excerpt, similarity, optional page). When no chunks pass the similarity threshold (or the user has no ready documents), Cortexa returns a fixed no-context answer, **empty citations**, `grounded=false`, and **does not call** the LLM.

## Manual embedding model pull

Embeddings are **not** downloaded automatically:

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

Also pull the chat model when you want generation:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

## Curl examples (host port 18000)

Replace the port if your `.env` uses defaults (`8000`). Cookie jar + bearer token workflow:

```bash
COOKIE_JAR="$(mktemp)"
BASE="http://localhost:18000"

# Register (sets HttpOnly refresh cookie; returns access_token)
curl -fsS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -X POST "$BASE/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"rag-demo@example.com","password":"StrongDemoPassword123!","full_name":"RAG Demo"}' \
  | tee /tmp/cortexa-auth.json

ACCESS="$(python3 -c 'import json; print(json.load(open("/tmp/cortexa-auth.json"))["access_token"])')"

# Embedding status (public)
curl -fsS "$BASE/api/v1/embeddings/status" | python3 -m json.tool

# Upload a text document
curl -fsS -H "Authorization: Bearer $ACCESS" \
  -F "file=@./README.md;type=text/markdown" \
  "$BASE/api/v1/documents" | python3 -m json.tool

# List documents
curl -fsS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/v1/documents" | python3 -m json.tool

# Grounded question
curl -fsS -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/rag/query" \
  -d '{"question":"What is Cortexa?","top_k":5}' | python3 -m json.tool

# Refresh access token via cookie
curl -fsS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
  -X POST "$BASE/api/v1/auth/refresh" | python3 -m json.tool

rm -f "$COOKIE_JAR" /tmp/cortexa-auth.json
```

## Frontend

When signed in, the home page shows a **Documents & grounded Q&A** panel: upload, list/delete, and ask questions with citation display. Access tokens remain **memory-only** (not `localStorage`).

## Configuration

See `.env.example` for `DOCUMENT_*`, `CHUNK_*`, `EMBEDDING_*`, and `RAG_*` settings.

## Known limitations (Phase 4)

- Synchronous ingest only — large files block the request (5 MiB cap mitigates this).
- No OCR, hybrid keyword search, or reranking.
- No multi-turn conversation memory or shared/org documents.
- Dense embeddings (e.g. `nomic-embed-text`) can assign non-trivial cosine similarity to loosely related text on tiny corpora; raise `RAG_MIN_SIMILARITY` (default `0.4`) if unrelated questions still retrieve chunks. Automated tests cover the strict no-context fallback path with fake embeddings.
- Document storage volume must be writable by the backend app user; the image entrypoint corrects ownership on start.
- Embedding and chat models are not auto-pulled — pull them manually before real RAG use.
