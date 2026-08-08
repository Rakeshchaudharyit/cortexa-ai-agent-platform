# GitHub Publication Checklist

Use this checklist immediately before making the repository public.

## Secrets and privacy

- [ ] `.env` is not tracked.
- [ ] `.env.example` contains placeholders only.
- [ ] no API tokens, OAuth secrets, passwords, private keys or production URLs are committed.
- [ ] no private customer documents, screenshots or database dumps are included.
- [ ] `git log -p` has been checked for historical secrets before publication.
- [ ] generated logs and runtime artifacts are excluded by `.gitignore`.

## Repository presentation

- [ ] root README renders correctly on GitHub.
- [ ] Mermaid architecture diagrams render.
- [ ] public landing/demo routes match README claims.
- [ ] demo knowledge files contain only synthetic/project documentation.
- [ ] development history is contained under `docs/archive/development-history/`.
- [ ] no public README section promotes experimental/disabled multi-agent functionality.

## Fresh-clone validation

From a clean clone:

```bash
cp .env.example .env
docker compose up -d --build
```

Then verify:

```bash
docker compose ps
make validate
```

Confirm the public landing page, login, workspace, Chat, admin dashboard, evaluations, feedback, analytics and jobs pages load successfully.

## GitHub settings

Recommended repository topics:

`fastapi`, `rag`, `pgvector`, `llm`, `nextjs`, `postgresql`, `redis`, `ai-evaluation`, `knowledge-management`, `python`, `typescript`, `docker`

Recommended About text:

> Enterprise AI knowledge platform with grounded RAG, pgvector, RAG evaluation, AI analytics, knowledge lifecycle and durable Redis/PostgreSQL background jobs.

## Before linking from Upwork

- [ ] repository is accessible in an incognito browser;
- [ ] README first screen clearly explains business value and stack;
- [ ] screenshots/demo video use the polished Portfolio Launch UI;
- [ ] live demo URL (when available) is added to README and Upwork portfolio;
- [ ] GitHub repository URL is added to the Upwork case study.
