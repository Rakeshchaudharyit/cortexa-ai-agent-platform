#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

echo "Cortexa release preflight"
./scripts/public-repo-check.sh

for path in .env.production.example docker-compose.production.yml Caddyfile frontend/Dockerfile.production backend/Dockerfile.production .github/workflows/ci.yml; do
  [[ -f "$path" ]] || { echo "ERROR: missing $path" >&2; exit 1; }
done

created_prod_env=0
if [[ ! -f .env.production ]]; then
  cp .env.production.example .env.production
  created_prod_env=1
fi
cleanup() {
  if [[ "$created_prod_env" -eq 1 ]]; then
    rm -f .env.production
  fi
}
trap cleanup EXIT

echo "[production compose] validating"
docker compose --env-file .env.production -f docker-compose.production.yml config >/dev/null

echo "[frontend production metadata] checking"
grep -q 'output: "standalone"' frontend/next.config.ts

echo "[repository status]"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git status --short
else
  echo "  git metadata not available in this package; skipped"
fi

echo "Release preflight: OK"
