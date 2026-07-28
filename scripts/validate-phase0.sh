#!/usr/bin/env bash
# Phase 0 local validation — structure, Compose, Python syntax, secret heuristics.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Repository tree"
if command -v tree >/dev/null 2>&1; then
  tree -a -I '.git|__pycache__|node_modules|.next'
else
  find . -path ./.git -prune -o -print | sed 's|[^/]*/|  |g'
fi

echo ""
echo "==> docker compose config"
docker compose config >/dev/null
echo "OK"

echo ""
echo "==> Python syntax (AST parse backend)"
python3 scripts/check-python-syntax.py

echo ""
echo "==> Secret heuristic scan"
if command -v rg >/dev/null 2>&1; then
  if rg -n --hidden -g '!.git/**' -g '!.env.example' \
      -e 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY' \
      -e 'AKIA[0-9A-Z]{16}' \
      . ; then
    echo "FAILED: possible secret material detected"
    exit 1
  fi
else
  if grep -R -n -E 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}' \
      --exclude-dir=.git --exclude=.env.example . ; then
    echo "FAILED: possible secret material detected"
    exit 1
  fi
fi
echo "OK"

echo ""
echo "==> git status"
git status --short

echo ""
echo "Phase 0 validation passed."
