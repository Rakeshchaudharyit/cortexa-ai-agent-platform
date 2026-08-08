#!/usr/bin/env bash
set -euo pipefail

fail=0

echo "Cortexa public repository preflight"

echo "[1/5] Secret/runtime files"
for path in .env .env.local .env.production .env.staging; do
  if [[ -f "$path" ]]; then
    echo "  note: $path exists locally; verify it is not tracked before publishing"
  fi
done
if [[ ! -f .env.example ]]; then
  echo "  ERROR: .env.example is missing"; fail=1
else
  echo "  .env.example: OK"
fi

echo "[2/5] Common generated directories"
for path in frontend/node_modules frontend/.next backend/.venv .venv; do
  if [[ -e "$path" ]]; then
    echo "  note: local generated path exists: $path (must remain ignored)"
  fi
done

echo "[3/5] Public documentation"
for path in README.md docs/ARCHITECTURE.md docs/ARCHITECTURE_DIAGRAMS.md docs/DEPLOYMENT.md docs/DEMO_GUIDE.md docs/PORTFOLIO_CASE_STUDY.md; do
  if [[ ! -f "$path" ]]; then echo "  ERROR: missing $path"; fail=1; fi
done
[[ $fail -eq 0 ]] && echo "  required docs: OK"

echo "[4/5] Development-history isolation"
if find . -maxdepth 1 -type f -name 'PHASE*.md' | grep -q .; then
  echo "  ERROR: phase files remain at repository root"; fail=1
else
  echo "  root phase files: clean"
fi

echo "[5/5] Obvious private-key patterns"
if command -v rg >/dev/null 2>&1; then
  if rg -n --hidden -g '!.git/**' -g '!**/node_modules/**' -g '!**/.next/**' -g '!docs/archive/**' 'BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|AKIA[0-9A-Z]{16}' .; then
    echo "  ERROR: possible secret material detected"; fail=1
  else
    echo "  key patterns: clean"
  fi
else
  echo "  rg not installed; rely on make secrets-check"
fi

if [[ $fail -ne 0 ]]; then
  echo "Public repository preflight: FAILED"
  exit 1
fi

echo "Public repository preflight: OK"
