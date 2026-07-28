#!/usr/bin/env python3
"""Parse all backend Python files for syntax errors (no bytecode writes)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "backend"
    errors = 0
    for path in sorted(root.rglob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors += 1
            print(f"syntax error: {path}: {exc}", file=sys.stderr)
    if errors:
        return 1
    print("python syntax: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
