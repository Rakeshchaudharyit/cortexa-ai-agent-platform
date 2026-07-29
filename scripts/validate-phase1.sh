#!/usr/bin/env bash
# Phase 1 validation suite — fails on first error.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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

echo "==> docker compose config"
docker compose config >/dev/null
echo "OK"

echo "==> secrets check"
make secrets-check

echo "==> alembic upgrade head"
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend alembic current

if docker compose ps --status running backend 2>/dev/null | grep -q backend; then
  echo "==> backend pytest (docker)"
  docker compose exec -T backend pytest
  echo "==> backend ruff check (docker)"
  docker compose exec -T backend ruff check .
  echo "==> backend ruff format --check (docker)"
  docker compose exec -T backend ruff format --check .
  echo "==> backend mypy (docker)"
  docker compose exec -T backend mypy app
else
  echo "==> backend checks require a running backend container"
  echo "    Run: docker compose up -d --build"
  exit 1
fi

if docker compose ps --status running frontend 2>/dev/null | grep -q frontend; then
  # Run as the cortexa app user so root-owned build artifacts do not break
  # the bind-mounted / named-volume .next tree used by `next dev`.
  echo "==> frontend lint (docker)"
  docker compose exec -T -u cortexa frontend npm run lint
  echo "==> frontend typecheck (docker)"
  docker compose exec -T -u cortexa frontend npm run typecheck
  echo "==> frontend test (docker)"
  docker compose exec -T -u cortexa frontend npm test -- --run
  echo "==> clear Next.js build cache (avoid stale .next collisions)"
  docker compose exec -T -u root frontend sh -c 'rm -rf /app/.next/cache /app/.next/server /app/.next/static /app/.next/types 2>/dev/null || true'
  echo "==> frontend build (docker)"
  docker compose exec -T -u cortexa frontend npm run build
  echo "==> restart frontend after production build (restore next dev)"
  docker compose restart frontend
  echo "==> wait for frontend health"
  for _ in $(seq 1 60); do
    if curl -fsS "http://localhost:${FRONTEND_PORT}/" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
else
  echo "==> frontend checks require a running frontend container"
  exit 1
fi

echo "==> health endpoint"
curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null
echo "OK"

echo "==> ready endpoint"
curl -fsS "http://localhost:${BACKEND_PORT}/ready" >/dev/null
echo "OK"

echo "==> system info endpoint"
curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/system/info" >/dev/null
echo "OK"

echo "==> llm status endpoint"
curl -fsS "http://localhost:${BACKEND_PORT}/api/v1/llm/status" >/dev/null
echo "OK"

echo "==> auth register/login/me smoke"
COOKIE_JAR="$(mktemp)"
REGISTER_EMAIL="validate-$(date +%s)@example.com"
curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${REGISTER_EMAIL}\",\"password\":\"StrongDemoPassword123!\",\"full_name\":\"Validate User\"}" \
  >/tmp/cortexa-auth-register.json
ACCESS_TOKEN="$(python3 -c 'import json; print(json.load(open("/tmp/cortexa-auth-register.json"))["access_token"])')"
curl -fsS -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "http://localhost:${BACKEND_PORT}/api/v1/auth/me" >/dev/null
curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/auth/refresh" >/tmp/cortexa-auth-refresh.json
ACCESS_TOKEN="$(python3 -c 'import json; print(json.load(open("/tmp/cortexa-auth-refresh.json"))["access_token"])')"
ANON_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/llm/generate" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}]}')"
if [[ "${ANON_CODE}" != "401" ]]; then
  echo "expected anonymous LLM generate to return 401, got ${ANON_CODE}"
  exit 1
fi
AUTH_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/llm/generate" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}]}')"
if [[ "${AUTH_CODE}" == "401" ]]; then
  echo "authenticated LLM generate must not return 401, got ${AUTH_CODE}"
  exit 1
fi
curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/auth/logout" >/dev/null
rm -f "${COOKIE_JAR}" /tmp/cortexa-auth-register.json /tmp/cortexa-auth-refresh.json
echo "OK"

echo "==> frontend HTTP"
curl -fsS "http://localhost:${FRONTEND_PORT}/" >/dev/null
echo "OK"

echo "==> frontend asset smoke"
python3 scripts/check_frontend_assets.py "http://localhost:${FRONTEND_PORT}"
echo "OK"

echo "==> frontend icon"
curl -fsS -o /dev/null "http://localhost:${FRONTEND_PORT}/icon.svg"
echo "OK"

echo ""
echo "Phase 1 + Phase 2 + Phase 3 validation: PASSED"
