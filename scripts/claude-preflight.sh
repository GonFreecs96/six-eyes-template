#!/bin/bash
# scripts/claude-preflight.sh — sourced by the headless `claude -p` orchestrators
# (six-eyes-run.sh, agent-pipeline-run.sh). Run from the repo root, BEFORE clearing
# any staging area. Resolves the claude binary onto PATH and fails fast (exit 1) if
# headless auth cannot actually make a call.

# Preflight: headless `claude -p` OAuth expires SEPARATELY from the interactive
# session, and an expired session fails every step instantly (~1s each) with the
# staging area already wiped — burning the whole run. Hit twice: 2026-08-03 and
# 2026-09-01, both requiring a manual `claude auth login` + full re-run (retro
# 2026-W36). Fail fast instead, before anything is cleared.
#
# Binary lookup: `claude` is often not on PATH (desktop-app installs bundle it under
# ~/Library/Application Support/Claude/claude-code/). Use CLAUDE_BIN if set, else PATH,
# else the newest bundled copy.
if [ -n "${CLAUDE_BIN:-}" ]; then
  PATH="$(dirname "$CLAUDE_BIN"):$PATH"
elif ! command -v claude >/dev/null 2>&1; then
  BUNDLED=$(ls -d "$HOME/Library/Application Support/Claude/claude-code"/*/*/claude.app/Contents/MacOS/claude 2>/dev/null | sort -V | tail -1)
  if [ -n "$BUNDLED" ]; then
    echo "claude not on PATH — using bundled binary: $BUNDLED"
    PATH="$(dirname "$BUNDLED"):$PATH"
  fi
fi
export PATH
if ! command -v claude >/dev/null 2>&1; then
  echo "FATAL: 'claude' binary not found (set CLAUDE_BIN=/path/to/claude)."
  exit 1
fi

# `claude auth status` reports logged-in even when the OAuth session can't refresh
# (2026-10-05: all four steps failed instantly with "OAuth session expired" after a
# passing status check). Make a real one-turn call instead.
if ! claude -p "reply ok" --model claude-haiku-4-5-20251001 --max-turns 1 \
    --output-format json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(1 if d.get('is_error') or d.get('terminal_reason')=='api_error' else 0)" 2>/dev/null; then
  echo "FATAL: headless claude auth is expired or unavailable (live test call failed)."
  echo "       Run 'claude auth login', then re-run this script."
  echo "       (Interactive auth does NOT imply headless auth — check both.)"
  exit 1
fi
