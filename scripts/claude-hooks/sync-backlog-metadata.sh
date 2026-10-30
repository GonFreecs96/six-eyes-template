#!/usr/bin/env bash
# Claude Code Stop hook: keep metadata/sixeyes.db + computed frontmatter in sync.
#
# Fires at the end of every Claude turn. If any data/backlog/*.md is newer than
# the SQLite DB (i.e. backlog files were edited this turn — by Claude, a
# promotion, or a git operation), run sync-metadata.py once. sync-metadata's
# final DB commit stamps the db mtime, so the -newer check self-resets and
# quiet turns cost one cheap find(1) call.
#
# Lives in scripts/claude-hooks/ (NOT scripts/hooks/, which install-hooks.sh
# symlinks into .git/hooks/ as git hooks).
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 0

DB="metadata/sixeyes.db"
[ -f "$DB" ] || exit 0

newest=$(find data/backlog -name '*.md' -newer "$DB" -print -quit 2>/dev/null)
[ -n "$newest" ] || exit 0

# Pass args through (the Stop hook passes --no-rotate so turn-end syncs don't
# rewrite data/state/*.json as an invisible side effect).
if python3 scripts/sync-metadata.py "$@" >/dev/null 2>&1; then
  echo '{"systemMessage":"Six Eyes: backlog changed this turn — sync-metadata.py ran (scores/staleness/DB refreshed)."}'
else
  echo '{"systemMessage":"Six Eyes: backlog changed this turn but sync-metadata.py FAILED — run it manually to see the error."}'
fi
exit 0
