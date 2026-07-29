#!/usr/bin/env bash
# Regression guard: never partially delete .next cache files while Next.js runs.
# Prefer: stop frontend → delete entire .next tree → restart/rebuild cleanly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "frontend cache safety: FAILED — $*" >&2
  exit 1
}

echo "==> scanning scripts for unsafe live .next cache deletion"

SCAN_TARGETS=(
  scripts/validate-phase1.sh
  scripts/validate-phase0.sh
  Makefile
  frontend/Dockerfile
)

TMP_HITS="$(mktemp)"
# shellcheck disable=SC2064
trap 'rm -f "${TMP_HITS}"' EXIT

: >"${TMP_HITS}"
for target in "${SCAN_TARGETS[@]}"; do
  [[ -f "${target}" ]] || continue
  grep -nE \
    'rm[[:space:]]+-rf[[:space:]].*\.next/cache|rm[[:space:]]+-rf[[:space:]].*\.next/\*|/\.next/cache/webpack|\.pack\.gz' \
    "${target}" >>"${TMP_HITS}" 2>/dev/null || true
done

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" ]] && continue
  # Allow whole-tree clears that use find -mindepth 1 (entrypoint / validate).
  if echo "${line}" | grep -Eq 'find /app/\.next -mindepth 1'; then
    continue
  fi
  fail "unsafe partial/live .next deletion pattern: ${line}"
done < "${TMP_HITS}"

if [[ -f scripts/validate-phase1.sh ]]; then
  if ! grep -q 'docker compose stop frontend' scripts/validate-phase1.sh; then
    fail "validate-phase1.sh must stop frontend before clearing .next"
  fi
  if grep -nE 'rm -rf /app/\.next/\*' scripts/validate-phase1.sh >/dev/null 2>&1; then
    fail "validate-phase1.sh must not use partial rm -rf /app/.next/*; clear the entire tree after stop"
  fi
  stop_line="$(grep -n 'docker compose stop frontend' scripts/validate-phase1.sh | head -1 | cut -d: -f1)"
  clear_line="$(grep -nE 'find /app/\.next|rm -rf /app/\.next' scripts/validate-phase1.sh | head -1 | cut -d: -f1 || true)"
  if [[ -z "${clear_line}" ]]; then
    fail "validate-phase1.sh must clear .next after stopping frontend"
  fi
  if [[ "${clear_line}" -le "${stop_line}" ]]; then
    fail "validate-phase1.sh must stop frontend before clearing .next"
  fi
fi

if [[ -f frontend/Dockerfile ]]; then
  if grep -nE '\.pack\.gz|/\.next/cache/webpack' frontend/Dockerfile >/dev/null 2>&1; then
    fail "frontend Dockerfile must not delete individual webpack pack files"
  fi
fi

echo "frontend cache safety: OK"
