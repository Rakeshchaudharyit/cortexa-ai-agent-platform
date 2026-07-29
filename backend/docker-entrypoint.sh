#!/bin/sh
# Ensure the document storage directory is writable by the app user.
set -eu

STORAGE_PATH="${DOCUMENT_STORAGE_PATH:-/var/lib/cortexa/documents}"
mkdir -p "$STORAGE_PATH"

if [ "$(id -u)" -eq 0 ]; then
  chown -R cortexa:cortexa "$STORAGE_PATH" || true
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u cortexa -- "$@"
  fi
  exec su -s /bin/sh cortexa -c 'exec "$@"' -- "$@"
fi

exec "$@"
