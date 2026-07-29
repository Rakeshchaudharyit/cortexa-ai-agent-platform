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

echo "==> health endpoint"
curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null
curl -fsS "http://localhost:${BACKEND_PORT}/health/live" >/dev/null
echo "OK"

echo "==> ready endpoint"
curl -fsS "http://localhost:${BACKEND_PORT}/ready" >/dev/null
curl -fsS "http://localhost:${BACKEND_PORT}/health/ready" >/dev/null
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
  -d "{\"email\":\"${REGISTER_EMAIL}\",\"password\":\"StrongDemoPassword123!\",\"confirm_password\":\"StrongDemoPassword123!\",\"full_name\":\"Validate User\"}" \
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

echo "==> conversations empty-list smoke"
COOKIE_JAR="$(mktemp)"
CONV_EMAIL="validate-conv-$(date +%s)@example.com"
curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${CONV_EMAIL}\",\"password\":\"StrongDemoPassword123!\",\"confirm_password\":\"StrongDemoPassword123!\",\"full_name\":\"Conv User\"}" \
  >/tmp/cortexa-conv-register.json
CONV_TOKEN="$(python3 -c 'import json; print(json.load(open("/tmp/cortexa-conv-register.json"))["access_token"])')"
CONV_LIST="$(curl -fsS -H "Authorization: Bearer ${CONV_TOKEN}" \
  "http://localhost:${BACKEND_PORT}/api/v1/conversations")"
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert d.get("total")==0 and d.get("items")==[], d' "${CONV_LIST}"
CONV_CREATE_CODE="$(curl -s -o /tmp/cortexa-conv-create.json -w "%{http_code}" \
  -H "Authorization: Bearer ${CONV_TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST "http://localhost:${BACKEND_PORT}/api/v1/conversations" \
  -d '{}')"
if [[ "${CONV_CREATE_CODE}" != "201" ]]; then
  echo "expected conversation create 201, got ${CONV_CREATE_CODE}"
  exit 1
fi
rm -f "${COOKIE_JAR}" /tmp/cortexa-conv-register.json /tmp/cortexa-conv-create.json
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

echo "==> frontend .next cache safety"
./scripts/check_frontend_cache_safety.sh
echo "OK"

echo ""
echo "Phase 1 + Phase 2 + Phase 3 + Phase 4 + Phase 5 validation: PASSED"
