#!/bin/sh
# Backend entrypoint:
# 1) Ensure document storage is writable
# 2) Apply Alembic migrations to head (before Uvicorn / connection pool)
# 3) Start the application process
#
# Migration failures must abort startup so the API never serves a missing schema.
# Applying migrations to an already-running backend requires a process restart so
# asyncpg does not retain stale type/relation caches across schema changes.
set -eu

STORAGE_PATH="${DOCUMENT_STORAGE_PATH:-/var/lib/cortexa/documents}"
mkdir -p "$STORAGE_PATH"

run_migrations() {
  echo "cortexa: applying database migrations (alembic upgrade head)"
  alembic upgrade head
  echo "cortexa: migrations applied successfully"
}

if [ "$(id -u)" -eq 0 ]; then
  chown -R cortexa:cortexa "$STORAGE_PATH" || true
  if command -v runuser >/dev/null 2>&1; then
    runuser -u cortexa -- sh -c 'alembic upgrade head'
    echo "cortexa: migrations applied successfully"
    exec runuser -u cortexa -- "$@"
  fi
  su -s /bin/sh cortexa -c 'alembic upgrade head'
  echo "cortexa: migrations applied successfully"
  exec su -s /bin/sh cortexa -c 'exec "$@"' -- "$@"
fi

run_migrations
exec "$@"
