# GitHub Publishing Guide

## Recommended repository identity

- **Repository name:** `cortexa-ai-knowledge-platform`
- **Description:** `Enterprise RAG knowledge platform with FastAPI, Next.js, pgvector, RAG evaluation, AI quality analytics, document governance and durable Redis workers.`
- **Visibility:** Public if source review is part of the portfolio strategy; otherwise public demo + private source is safer.
- **Website:** set this to the live demo URL after deployment.

Recommended topics:

`fastapi`, `python`, `rag`, `llm`, `pgvector`, `postgresql`, `nextjs`, `typescript`, `redis`, `ollama`, `ai-evaluation`, `knowledge-management`, `docker`, `enterprise-ai`

## Clean publication sequence

1. Run `./scripts/release-preflight.sh`.
2. Run the full local `make validate` gate.
3. Confirm `.env`, `.env.production`, uploads, databases and generated files are not tracked.
4. Review `git status` and the staged diff.
5. Create a clean portfolio release commit rather than publishing dozens of local debugging artifacts.
6. Push `main` and verify Repository CI is green.
7. Add the live demo URL to the GitHub repository website field and README only after it resolves successfully.

## Suggested release commit

```text
release: portfolio-ready Cortexa AI Knowledge Platform
```

## Suggested first tag

```text
v1.0.0-portfolio
```

The Git tag is a portfolio/release marker; it does not need to mirror historical internal phase numbering.
