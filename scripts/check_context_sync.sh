#!/usr/bin/env bash
# Drift enforcement for the Six Eyes context layer (template: two-step check).
#
#   1. scripts/export_context.py --check    (bq-knowledge.md -> config/context/*.yaml)
#   2. scripts/check_schema_meta.py --check (context -> config/schemas meta.business_rules)
#
# Used by scripts/hooks/pre-commit and .github/workflows/context-sync.yml
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
else
  PY="python3"
fi

fail=0

echo "[context-sync] export_context.py --check"
if ! "$PY" scripts/export_context.py --check; then
  echo "  -> config/context/*.yaml is stale. Run: $PY scripts/export_context.py" >&2
  fail=1
fi

echo "[context-sync] check_schema_meta.py --check"
if ! "$PY" scripts/check_schema_meta.py --check; then
  echo "  -> schema meta lock drifted. Run: $PY scripts/check_schema_meta.py" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "[context-sync] FAILED — regenerate context layer and re-stage." >&2
  exit 1
fi

echo "[context-sync] OK — context layer in sync."
