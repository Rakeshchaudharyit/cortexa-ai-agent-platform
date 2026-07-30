#!/usr/bin/env bash
# Capture / compare development database counts around validation.
# Read-only against cortexa_agent. Never prints passwords, hashes, or tokens.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-}"
SNAPSHOT_DIR="${CORTEXA_VALIDATE_SNAPSHOT_DIR:-/tmp/cortexa-validate-dev-snapshot}"
EXPECTED_PROJECT="${COMPOSE_PROJECT_NAME:-cortexa}"
COMPOSE=(docker compose -p "$EXPECTED_PROJECT")
KNOWN_EMAIL="${CORTEXA_KNOWN_DEV_EMAIL:-chaudharyrakeshit@gmail.com}"

usage() {
  echo "Usage: $0 before|after|compare" >&2
  exit 2
}

require_dev_postgres() {
  if ! "${COMPOSE[@]}" ps --status running postgres 2>/dev/null | grep -q postgres; then
    echo "verify_validation_preserves_dev_data: FAILED — development postgres is not running" >&2
    exit 1
  fi
}

mounted_volume() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q postgres)"
  docker inspect "$cid" --format \
    '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}'
}

capture_snapshot() {
  local out="$1"
  mkdir -p "$SNAPSHOT_DIR"
  require_dev_postgres

  local volume db_name identity users documents conversations messages known_id
  volume="$(mounted_volume)"
  db_name="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc 'SELECT current_database();' | tr -d '\r')"
  identity="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc \
    "SELECT value FROM application_metadata WHERE key='database_identity';" | tr -d '\r')"
  users="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc 'SELECT count(*) FROM users;' | tr -d '\r')"
  documents="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc 'SELECT count(*) FROM documents;' | tr -d '\r')"
  conversations="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc 'SELECT count(*) FROM conversations;' | tr -d '\r')"
  messages="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc 'SELECT count(*) FROM messages;' | tr -d '\r')"
  known_id="$("${COMPOSE[@]}" exec -T postgres psql -U cortexa -d cortexa_agent -Atc \
    "SELECT COALESCE((SELECT id::text FROM users WHERE lower(email)=lower('${KNOWN_EMAIL}') LIMIT 1), '');" | tr -d '\r')"

  if [[ "$db_name" != "cortexa_agent" ]]; then
    echo "verify_validation_preserves_dev_data: FAILED — unexpected database '$db_name'" >&2
    exit 1
  fi
  if [[ "$identity" != "cortexa-agent-development" ]]; then
    echo "verify_validation_preserves_dev_data: FAILED — unexpected identity '$identity'" >&2
    exit 1
  fi
  if [[ "$volume" != "cortexa_postgres_data" ]]; then
    echo "verify_validation_preserves_dev_data: FAILED — unexpected volume '$volume'" >&2
    exit 1
  fi

  cat >"$out" <<EOF
database_name=${db_name}
database_identity=${identity}
postgres_volume=${volume}
users=${users}
documents=${documents}
conversations=${conversations}
messages=${messages}
known_email=${KNOWN_EMAIL}
known_user_id=${known_id}
EOF

  echo "snapshot written: $out"
  echo "  database=${db_name} identity=${identity} volume=${volume}"
  echo "  users=${users} documents=${documents} conversations=${conversations} messages=${messages}"
  if [[ -n "$known_id" ]]; then
    echo "  known user present id=${known_id}"
  else
    echo "  known user absent (email recorded for post-check disappearance detection)"
  fi
}

compare_snapshots() {
  local before="${SNAPSHOT_DIR}/before.env"
  local after="${SNAPSHOT_DIR}/after.env"
  if [[ ! -f "$before" || ! -f "$after" ]]; then
    echo "verify_validation_preserves_dev_data: FAILED — missing before/after snapshots" >&2
    exit 1
  fi

  # shellcheck disable=SC1090
  source "$before"
  local b_db="$database_name" b_id="$database_identity" b_vol="$postgres_volume"
  local b_users="$users" b_docs="$documents" b_convs="$conversations" b_msgs="$messages"
  local b_known="$known_user_id"

  # shellcheck disable=SC1090
  source "$after"
  local a_db="$database_name" a_id="$database_identity" a_vol="$postgres_volume"
  local a_users="$users" a_docs="$documents" a_convs="$conversations" a_msgs="$messages"
  local a_known="$known_user_id"

  local failed=0
  compare_field() {
    local label="$1" left="$2" right="$3"
    if [[ "$left" != "$right" ]]; then
      echo "CHANGED: ${label}: before=${left} after=${right}" >&2
      failed=1
    else
      echo "unchanged: ${label}=${left}"
    fi
  }

  compare_field database_name "$b_db" "$a_db"
  compare_field database_identity "$b_id" "$a_id"
  compare_field postgres_volume "$b_vol" "$a_vol"
  compare_field users "$b_users" "$a_users"
  compare_field documents "$b_docs" "$a_docs"
  compare_field conversations "$b_convs" "$a_convs"
  compare_field messages "$b_msgs" "$a_msgs"

  if [[ -n "$b_known" && -z "$a_known" ]]; then
    echo "CHANGED: known user disappeared (was id=${b_known})" >&2
    failed=1
  elif [[ -n "$b_known" && -n "$a_known" && "$b_known" != "$a_known" ]]; then
    echo "CHANGED: known user id before=${b_known} after=${a_known}" >&2
    failed=1
  else
    echo "unchanged: known_user_id=${a_known:-absent}"
  fi

  if [[ "$failed" -ne 0 ]]; then
    echo "verify_validation_preserves_dev_data: FAILED — development data changed during validation" >&2
    exit 1
  fi
  echo "verify_validation_preserves_dev_data: OK"
}

case "$MODE" in
  before)
    capture_snapshot "${SNAPSHOT_DIR}/before.env"
    ;;
  after)
    capture_snapshot "${SNAPSHOT_DIR}/after.env"
    ;;
  compare)
    compare_snapshots
    ;;
  *)
    usage
    ;;
esac
