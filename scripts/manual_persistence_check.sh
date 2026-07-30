#!/usr/bin/env bash
# Manual persistence checklist for local Compose (never uses down -v).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EMAIL="${1:-}"
if [[ -z "$EMAIL" ]]; then
  echo "Usage: $0 <email>" >&2
  exit 2
fi

BACKEND_PORT="$(docker compose exec -T backend printenv BACKEND_PORT 2>/dev/null | tr -d '\r' || true)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
# Host-mapped port from .env when remapped (e.g. 18000)
HOST_BACKEND_PORT="${HOST_BACKEND_PORT:-}"
if [[ -z "$HOST_BACKEND_PORT" && -f .env ]]; then
  HOST_BACKEND_PORT="$(awk -F= '/^BACKEND_PORT=/{print $2; exit}' .env | tr -d '\r' || true)"
fi
HOST_BACKEND_PORT="${HOST_BACKEND_PORT:-$BACKEND_PORT}"
BASE="http://127.0.0.1:${HOST_BACKEND_PORT}"

echo "==> compose identity"
./scripts/check_compose_identity.sh

echo "==> confirm user exists (email value not printed; id/status/hash metadata only)"
docker compose exec -T postgres \
  psql -U cortexa -d cortexa_agent -v ON_ERROR_STOP=1 -v email="$EMAIL" \
  -c "SELECT id, created_at, status::text, left(password_hash,12) AS hash_prefix, length(password_hash) AS hash_len FROM users WHERE lower(trim(email)) = lower(trim(:'email'));"

echo "==> login after backend restart"
docker compose restart backend
sleep 5
curl -fsS "$BASE/ready" >/dev/null
echo "ready after backend restart: OK"
echo "(Perform interactive login in the browser or via curl with getpass locally.)"

echo "==> full compose down/up without -v"
docker compose down
docker compose up -d
sleep 15
./scripts/check_compose_identity.sh
curl -fsS "$BASE/ready" >/dev/null
echo "ready after compose restart: OK"
echo "Manual persistence check complete. Volumes were preserved (no -v)."
