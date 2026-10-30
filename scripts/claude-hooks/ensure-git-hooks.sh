#!/usr/bin/env bash
# Claude Code SessionStart hook: make sure the tracked git pre-commit hook
# (scripts/hooks/pre-commit, installed as a symlink by scripts/install-hooks.sh)
# is present in this clone, so a fresh clone can't skip the pre-commit checks.
#
# Cases:
#   valid symlink            -> silent no-op
#   missing / dangling link  -> auto-install, tell the operator
#   foreign regular file     -> do NOT touch it (install-hooks.sh would move it
#                               aside); tell the operator to resolve manually
#   no .git/hooks dir        -> silent no-op (worktree / non-clone)
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 0

DEST=".git/hooks/pre-commit"
[ -d ".git/hooks" ] || exit 0

if [ -L "$DEST" ] && [ -e "$DEST" ]; then
  exit 0  # healthy symlink
fi

if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
  echo '{"systemMessage":"Six Eyes: .git/hooks/pre-commit is a regular file, not the tracked symlink — the context-sync hook is NOT active. Run scripts/install-hooks.sh yourself to back it up and install (not auto-run to avoid clobbering your file)."}'
  exit 0
fi

# Missing entirely, or a dangling symlink (safe to overwrite).
if bash scripts/install-hooks.sh >/dev/null 2>&1; then
  echo '{"systemMessage":"Six Eyes: git pre-commit hook was missing — installed via scripts/install-hooks.sh."}'
else
  echo '{"systemMessage":"Six Eyes: git pre-commit hook is missing and scripts/install-hooks.sh FAILED — run it manually."}'
fi
exit 0
