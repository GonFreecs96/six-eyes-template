#!/usr/bin/env bash
# Install the tracked git hooks (scripts/hooks/*) into this clone's .git/hooks/.
#
# git does not version-control .git/hooks/, so the canonical hooks live under
# scripts/hooks/ and this installer symlinks them in. Run once per clone:
#
#   scripts/install-hooks.sh
#
# Re-runnable and idempotent. Backs up any pre-existing non-symlink hook.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/scripts/hooks"
DEST_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$DEST_DIR" ]; then
  echo "error: $DEST_DIR not found — is this a git clone?" >&2
  exit 1
fi

for hook_path in "$SRC_DIR"/*; do
  [ -f "$hook_path" ] || continue
  hook="$(basename "$hook_path")"
  dest="$DEST_DIR/$hook"
  chmod +x "$hook_path"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    mv "$dest" "$dest.backup.$(date +%s)"
    echo "backed up existing $hook"
  fi
  ln -sf "../../scripts/hooks/$hook" "$dest"
  echo "installed $hook -> scripts/hooks/$hook"
done

echo "done."
