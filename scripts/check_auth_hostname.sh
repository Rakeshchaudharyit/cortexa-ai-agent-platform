#!/usr/bin/env bash
# Fail when browser-facing auth hosts are mixed (localhost vs 127.0.0.1).
# SameSite=Lax refresh cookies are host-bound; mixing breaks session restore.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

env_get() {
  local key="$1"
  local file="${2:-.env}"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  # Read KEY=value without sourcing (APP_NAME may contain spaces).
  local line
  line="$(grep -E "^${key}=" "$file" | tail -n1 || true)"
  if [[ -z "$line" ]]; then
    return 0
  fi
  printf '%s' "${line#*=}"
}

API_URL="${NEXT_PUBLIC_API_BASE_URL:-$(env_get NEXT_PUBLIC_API_BASE_URL)}"
FRONT_ORIGIN="${FRONTEND_ORIGIN:-$(env_get FRONTEND_ORIGIN)}"
RESET_URL="${PASSWORD_RESET_FRONTEND_URL:-$(env_get PASSWORD_RESET_FRONTEND_URL)}"

host_of() {
  python3 -c 'import sys, urllib.parse as u; print(u.urlparse(sys.argv[1]).hostname or "")' "$1"
}

echo "==> auth hostname consistency check"

if [[ -z "$API_URL" || -z "$FRONT_ORIGIN" ]]; then
  echo "auth hostname: SKIPPED — NEXT_PUBLIC_API_BASE_URL or FRONTEND_ORIGIN unset"
  exit 0
fi

API_HOST="$(host_of "$API_URL")"
FRONT_HOST="$(host_of "$FRONT_ORIGIN")"

if [[ -z "$API_HOST" || -z "$FRONT_HOST" ]]; then
  echo "auth hostname: FAILED — could not parse hosts from:" >&2
  echo "  NEXT_PUBLIC_API_BASE_URL=$API_URL" >&2
  echo "  FRONTEND_ORIGIN=$FRONT_ORIGIN" >&2
  exit 1
fi

if [[ "$API_HOST" != "$FRONT_HOST" ]]; then
  echo "auth hostname: FAILED — hostname mismatch breaks SameSite refresh cookies" >&2
  echo "  NEXT_PUBLIC_API_BASE_URL host: $API_HOST ($API_URL)" >&2
  echo "  FRONTEND_ORIGIN host:          $FRONT_HOST ($FRONT_ORIGIN)" >&2
  echo "Use the same host (both 127.0.0.1 or both localhost) everywhere." >&2
  exit 1
fi

if [[ -n "$RESET_URL" ]]; then
  RESET_HOST="$(host_of "$RESET_URL")"
  if [[ -n "$RESET_HOST" && "$RESET_HOST" != "$FRONT_HOST" ]]; then
    echo "auth hostname: FAILED — PASSWORD_RESET_FRONTEND_URL host '$RESET_HOST' != '$FRONT_HOST'" >&2
    exit 1
  fi
fi

echo "auth hosts aligned on: $API_HOST (ok)"
echo "auth hostname: OK"
