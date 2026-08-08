# Cortexa Frontend

Next.js + TypeScript frontend for the Cortexa AI Knowledge Platform.

## Main product surfaces

- public landing page (`/`)
- guided product tour (`/demo`)
- authenticated workspace (`/workspace`)
- grounded knowledge chat (`/chat`)
- memories and safe AI tools
- enterprise admin console (`/admin/*`)
- RAG evaluations, feedback review and AI analytics
- background operations/job monitoring

## API access

The browser uses `NEXT_PUBLIC_API_BASE_URL` for client-side API requests. Access tokens remain memory-only; refresh sessions use HttpOnly cookies. Streaming chat uses `fetch` + `ReadableStream` so authorization headers and SSE-style streaming can coexist.

For local development, keep the browser frontend/API hostnames consistent (`localhost` with `localhost`, or `127.0.0.1` with `127.0.0.1`) so refresh-cookie behavior remains predictable.

## Docker development

Compose bind-mounts the frontend source into `/app` for development and keeps `node_modules` / `.next` in container-owned named volumes.

See the root [README](../README.md) and [Demo Guide](../docs/DEMO_GUIDE.md).
