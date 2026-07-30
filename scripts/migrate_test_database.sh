#!/usr/bin/env bash
# Migrate cortexa_agent_test and set durable test identity.
# Never targets cortexa_agent / cortexa-agent-development.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE=(env COMPOSE_IGNORE_ORPHANS=1 docker compose -p cortexa-test -f docker-compose.test.yml)

echo "==> waiting for postgres-test"
"${COMPOSE[@]}" up -d postgres-test redis-test
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T postgres-test pg_isready -U cortexa -d cortexa_agent_test >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

DB_NAME="$("${COMPOSE[@]}" exec -T postgres-test psql -U cortexa -d cortexa_agent_test -Atc 'SELECT current_database();' | tr -d '\r')"
if [[ "$DB_NAME" != "cortexa_agent_test" ]]; then
  echo "test-db-migrate: FAILED — refused database '$DB_NAME'" >&2
  exit 1
fi

echo "==> alembic upgrade head (cortexa_agent_test)"
"${COMPOSE[@]}" run --rm --no-deps backend-test \
  "alembic upgrade head"

echo "==> set database identity to cortexa-agent-test"
"${COMPOSE[@]}" exec -T postgres-test psql -U cortexa -d cortexa_agent_test -v ON_ERROR_STOP=1 <<'SQL'
UPDATE application_metadata
SET value = 'cortexa-agent-test',
    updated_at = now()
WHERE key = 'database_identity';

SELECT key, value
FROM application_metadata
ORDER BY key;
SQL

IDENTITY="$("${COMPOSE[@]}" exec -T postgres-test psql -U cortexa -d cortexa_agent_test -Atc \
  "SELECT value FROM application_metadata WHERE key='database_identity';" | tr -d '\r')"
if [[ "$IDENTITY" != "cortexa-agent-test" ]]; then
  echo "test-db-migrate: FAILED — identity is '$IDENTITY'" >&2
  exit 1
fi

echo "test-db-migrate: OK (database=cortexa_agent_test identity=cortexa-agent-test)"
