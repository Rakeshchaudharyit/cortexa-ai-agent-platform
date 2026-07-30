#!/usr/bin/env bash
# Phase 1–5.1 validation suite — fails on first error.
# Backend pytest runs ONLY against cortexa_agent_test via docker-compose.test.yml.
# Development cortexa_agent must remain unmodified (enforced by preserve scripts).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE_TEST=(env COMPOSE_IGNORE_ORPHANS=1 docker compose -p cortexa-test -f docker-compose.test.yml)

# Load host port overrides from `.env` without sourcing free-form values
# (APP_NAME and similar may contain spaces and are unsafe to `source`).
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ''|\#*) continue ;;
      BACKEND_PORT=*|FRONTEND_PORT=*)
        key="${line%%=*}"
        value="${line#*=}"
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        printf -v "$key" '%s' "$value"
        export "$key"
        ;;
    esac
  done < .env
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

echo "==> docker compose config (development)"
docker compose config >/dev/null
echo "OK"

echo "==> docker compose config (test)"
"${COMPOSE_TEST[@]}" config >/dev/null
echo "OK"

echo "==> secrets check"
make secrets-check

echo "==> alembic current/heads (development — read-only check)"
docker compose exec -T backend alembic current
docker compose exec -T backend alembic heads

echo "==> isolated test services up + migrate cortexa_agent_test"
make test-services-up
make test-db-migrate

echo "==> backend pytest (isolated cortexa_agent_test ONLY)"
"${COMPOSE_TEST[@]}" run --rm backend-test "pytest"
echo "==> backend ruff check (isolated runner)"
"${COMPOSE_TEST[@]}" run --rm --no-deps backend-test "ruff check ."
echo "==> backend ruff format --check (isolated runner)"
"${COMPOSE_TEST[@]}" run --rm --no-deps backend-test "ruff format --check ."
echo "==> backend mypy (isolated runner)"
"${COMPOSE_TEST[@]}" run --rm --no-deps backend-test "mypy app"

if docker compose ps --status running frontend 2>/dev/null | grep -q frontend; then
  # Run as the cortexa app user so root-owned build artifacts do not break
  # the bind-mounted / named-volume .next tree used by `next dev`.
  echo "==> frontend lint (docker)"
  docker compose exec -T -u cortexa frontend npm run lint
  echo "==> frontend typecheck (docker)"
  docker compose exec -T -u cortexa frontend npm run typecheck
  echo "==> frontend test (docker)"
  docker compose exec -T -u cortexa frontend npm test -- --run

  # Never delete selected files inside .next while Next.js is running.
  # Stop the frontend, wipe the entire .next volume tree, build, then restart.
  echo "==> stop frontend before clearing .next"
  docker compose stop frontend
  echo "==> clear entire Next.js .next directory (volume-safe)"
  docker compose run --rm --no-deps -u root --entrypoint sh frontend -c '
    set -eu
    if [ -d /app/.next ]; then
      find /app/.next -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    fi
    mkdir -p /app/.next
    chown -R cortexa:cortexa /app/.next
  '
  echo "==> frontend build (docker, Next stopped)"
  docker compose run --rm --no-deps -u cortexa --entrypoint sh frontend -c 'npm run build'
  echo "==> start frontend (clean next dev)"
  docker compose up -d frontend
  echo "==> wait for frontend health"
  for _ in $(seq 1 90); do
    if curl -fsS "http://localhost:${FRONTEND_PORT}/" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
else
  echo "==> frontend checks require a running frontend container"
  exit 1
fi

echo "==> health endpoint (development — read-only)"
curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null
curl -fsS "http://localhost:${BACKEND_PORT}/health/live" >/dev/null
echo "OK"

echo "==> ready endpoint (development — read-only)"
curl -fsS "http://localhost:${BACKEND_PORT}/ready" >/dev/null
curl -fsS "http://localhost:${BACKEND_PORT}/health/ready" >/dev/null
echo "OK"

echo "==> system info endpoint (development — read-only)"
curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/system/info" >/dev/null
echo "OK"

echo "==> llm status endpoint (development — read-only)"
curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/llm/status" >/dev/null
echo "OK"

echo "==> anonymous LLM generate must be 401 (development — no writes)"
ANON_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/llm/generate" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}]}')"
if [[ "${ANON_CODE}" != "401" ]]; then
  echo "expected anonymous LLM generate to return 401, got ${ANON_CODE}"
  exit 1
fi
echo "OK"

# Auth register/login/conversation smoke previously wrote validate-* users into
# cortexa_agent and was wiped by pytest DELETE FROM users. Auth lifecycle is
# covered by isolated backend pytest against cortexa_agent_test instead.

echo "==> frontend HTTP"
curl -fsS "http://localhost:${FRONTEND_PORT}/" >/dev/null
echo "OK"

echo "==> frontend asset smoke"
python3 scripts/check_frontend_assets.py "http://localhost:${FRONTEND_PORT}"
echo "OK"

echo "==> frontend icon"
curl -fsS -o /dev/null "http://localhost:${FRONTEND_PORT}/icon.svg"
echo "OK"

echo "==> frontend .next cache safety"
./scripts/check_frontend_cache_safety.sh
echo "OK"

echo "==> stop isolated test services (retain test volume; never -v on development)"
make test-services-down

echo ""
echo "Phase 1 + Phase 2 + Phase 3 + Phase 4 + Phase 5 validation: PASSED"
echo "(development database was not used for pytest cleanup)"
