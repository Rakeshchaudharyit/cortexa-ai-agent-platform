#!/usr/bin/env bash
# Fail when the Compose project / Postgres volume identity drifts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

EXPECTED_PROJECT="${COMPOSE_PROJECT_NAME:-cortexa}"
EXPECTED_VOLUME="${EXPECTED_POSTGRES_VOLUME:-cortexa_postgres_data}"
EXPECTED_DB="${POSTGRES_DB:-cortexa_agent}"
COMPOSE=(docker compose -p "$EXPECTED_PROJECT")

echo "==> compose identity check"
CONFIG_NAME="$("${COMPOSE[@]}" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name",""))')"
if [[ "$CONFIG_NAME" != "$EXPECTED_PROJECT" ]]; then
  echo "compose identity: FAILED — project name '$CONFIG_NAME' != '$EXPECTED_PROJECT'" >&2
  exit 1
fi
echo "compose project name: $CONFIG_NAME (ok)"

VOLUMES="$("${COMPOSE[@]}" config --volumes)"
if ! grep -qx "$EXPECTED_VOLUME" <<<"$VOLUMES"; then
  echo "compose identity: FAILED — expected volume '$EXPECTED_VOLUME' not in:" >&2
  echo "$VOLUMES" >&2
  exit 1
fi
echo "compose volume declaration: $EXPECTED_VOLUME (ok)"

if "${COMPOSE[@]}" ps --status running postgres 2>/dev/null | grep -q postgres; then
  CID="$("${COMPOSE[@]}" ps -q postgres)"
  MOUNT_NAME="$(docker inspect "$CID" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}')"
  if [[ "$MOUNT_NAME" != "$EXPECTED_VOLUME" ]]; then
    echo "compose identity: FAILED — mounted postgres volume '$MOUNT_NAME' != '$EXPECTED_VOLUME'" >&2
    exit 1
  fi
  echo "mounted postgres volume: $MOUNT_NAME (ok)"

  DB_NAME="$("${COMPOSE[@]}" exec -T postgres printenv POSTGRES_DB | tr -d '\r')"
  if [[ "$DB_NAME" != "$EXPECTED_DB" ]]; then
    echo "compose identity: FAILED — POSTGRES_DB '$DB_NAME' != '$EXPECTED_DB'" >&2
    exit 1
  fi
  echo "postgres database: $DB_NAME (ok)"
else
  echo "postgres not running — skipped live mount/db checks"
fi

echo "compose identity: OK"
