#!/usr/bin/env bash
# Destructive database reset — requires typed confirmation. Never used by make down.
# Never uses `docker compose down -v` (preserves Redis/Ollama/documents volumes).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Prefer Compose-resolved APP_ENV (includes .env) over a bare host variable alone.
COMPOSE_APP_ENV="$(
  docker compose config --format json 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(((d.get("services") or {}).get("backend") or {}).get("environment") or {}).get("APP_ENV","")' \
    2>/dev/null || true
)"
EFFECTIVE_APP_ENV="${COMPOSE_APP_ENV:-${APP_ENV:-development}}"
if [[ "$EFFECTIVE_APP_ENV" == "production" ]]; then
  echo "Refusing destructive reset in production." >&2
  exit 2
fi

EXPECTED="RESET CORTEXA DEV DATABASE"
echo "WARNING: This will stop Compose and delete the named volume cortexa_postgres_data."
echo "An automatic pg_dump backup will be attempted first when postgres is running."
echo "Type exactly: $EXPECTED"
read -r CONFIRM
if [[ "$CONFIRM" != "$EXPECTED" ]]; then
  echo "Confirmation mismatch — aborting." >&2
  exit 1
fi

mkdir -p backups/database-recovery
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
  echo "==> backing up cortexa_agent before reset"
  docker compose exec -T postgres \
    pg_dump -U cortexa -d cortexa_agent -Fc \
    > "backups/database-recovery/cortexa_agent-before-reset-${STAMP}.dump"
  ls -la "backups/database-recovery/cortexa_agent-before-reset-${STAMP}.dump"
fi

echo "==> bringing stack down (without -v) so the postgres volume can be removed"
docker compose down
docker volume rm cortexa_postgres_data
docker compose up -d --build
echo "Destructive reset complete. Re-run migrations via backend entrypoint / make migrate."
