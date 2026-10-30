#!/usr/bin/env python3
"""Conflict-aware promote for the /six-eyes-run staging gate.

Staged files under data/staging/staged/ are snapshots taken when the `claude -p`
steps ran, often 30-60 min before promote. A blind `cp` silently reverts anything
another session changed in the meantime (for example concurrent edits to
`data/bq-knowledge.md`). This script makes blind overwrites impossible:

  record-base   (six-eyes-run.sh, before Step 1) — write data/staging/run-base.json:
                the start HEAD plus a blob for every file that was dirty or untracked
                at that moment (`git hash-object -w`), so the exact pre-run content of
                any path can be recovered later.
  check         (gate, Step 1) — classify every staged file: create / overwrite /
                CONFLICT-merge / CONFLICT-skip. A file conflicts when its live content
                differs from its run-start content — this covers commits landed since
                the start HEAD and uncommitted working-tree edits alike.
  promote       (Step 2) — copy non-conflicted files as before; 3-way merge
                (`git merge-file live base staged`) the append-style ones; skip the rest.
                Never writes a conflict-marked file to its live path.

Append-style (mergeable) paths: data/bq-knowledge.md and data/backlog/*.md (whole
file — Notes / Meeting Notes appends from both sides merge cleanly). Conflict hunks
that touch only the computed frontmatter fields (escalation_level / stale_weeks /
priority_score) resolve to the live side, since sync-metadata.py recomputes them
after promote anyway (Step 3). Every other conflicting path is skipped and reported.

Exit codes: check/promote exit 0 when nothing needs the operator's attention, 2 when there
are conflicts (check) or skipped/unmerged files (promote), 1 on usage errors.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGING = Path("data/staging")
STAGED = STAGING / "staged"
BASE_FILE = STAGING / "run-base.json"
CONFLICT_DIR = STAGING / "conflicts"

MERGEABLE = ["data/bq-knowledge.md", "data/backlog/*.md"]
COMPUTED_FIELD_RE = re.compile(r"^(escalation_level|stale_weeks|priority_score):")


def git(*args: str, check: bool = True, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, check=check, input=input_bytes)


def hash_file(rel: str, write: bool = False) -> str:
    args = ["hash-object", *(["-w"] if write else []), "--", rel]
    return git(*args).stdout.decode().strip()


# --------------------------------------------------------------------------- base


def record_base() -> dict:
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    # Dirty tracked files (staged or not) + untracked, non-ignored files: their
    # run-start content isn't in HEAD, so store it as a blob now.
    dirty = set(git("diff", "--name-only", "-z", "HEAD").stdout.decode().split("\0"))
    dirty |= set(git("ls-files", "-z", "--others", "--exclude-standard").stdout.decode().split("\0"))
    blobs: dict[str, str | None] = {}
    for rel in sorted(p for p in dirty if p and not p.startswith(str(STAGING) + "/")):
        blobs[rel] = hash_file(rel, write=True) if (REPO_ROOT / rel).is_file() else None  # None = deleted
    base = {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "head": head,
        "dirty": blobs,
    }
    (REPO_ROOT / STAGING).mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / BASE_FILE).write_text(json.dumps(base, indent=2) + "\n")
    return base


def load_base() -> dict | None:
    p = REPO_ROOT / BASE_FILE
    return json.loads(p.read_text()) if p.exists() else None


def base_blob(base: dict, rel: str) -> str | None:
    """Blob id of `rel` as it was at run start, or None if it didn't exist."""
    if rel in base["dirty"]:
        return base["dirty"][rel]
    r = git("rev-parse", "--verify", "--quiet", f"{base['head']}:{rel}", check=False)
    return r.stdout.decode().strip() or None


# --------------------------------------------------------------------------- check


def is_mergeable(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in MERGEABLE)


def staged_files() -> list[str]:
    root = REPO_ROOT / STAGED
    if not root.is_dir():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def classify(base: dict | None, rel: str) -> dict:
    live = REPO_ROOT / rel
    exists = live.is_file()
    row = {"path": rel, "action": "overwrite" if exists else "create", "conflict": False, "reason": ""}
    if base is None:
        row["action"] += " (unverified: no run-base.json)"
        return row
    b = base_blob(base, rel)
    if exists:
        live_blob = hash_file(rel)
        if b is None:
            row.update(conflict=True, reason="created by someone else since run start")
        elif live_blob != b:
            row.update(conflict=True, reason="changed since run start")
    elif b is not None:
        row.update(conflict=True, reason="deleted since run start")
    if row["conflict"]:
        row["action"] = "CONFLICT-merge" if (is_mergeable(rel) and exists and b) else "CONFLICT-skip"
    if row["conflict"] and exists:
        changed_in_commits = git("diff", "--name-only", base["head"], "HEAD", "--", rel).stdout.strip()
        row["reason"] += " (committed)" if changed_in_commits else " (uncommitted working-tree edit)"
    return row


def check(base: dict | None) -> list[dict]:
    return [classify(base, rel) for rel in staged_files()]


# --------------------------------------------------------------------------- merge

HUNK_RE = re.compile(r"^<<<<<<< .*?\n(.*?)^=======\n(.*?)^>>>>>>> .*?\n", re.S | re.M)


def resolve_computed_only(text: str) -> tuple[str, int]:
    """Resolve conflict hunks whose lines are all computed frontmatter fields to the
    live (ours) side. Returns (text, remaining_conflicts)."""
    remaining = 0

    def repl(m: re.Match) -> str:
        nonlocal remaining
        ours, theirs = m.group(1), m.group(2)
        lines = [l for l in (ours + theirs).splitlines() if l.strip()]
        if lines and all(COMPUTED_FIELD_RE.match(l) for l in lines):
            return ours
        remaining += 1
        return m.group(0)

    return HUNK_RE.sub(repl, text), remaining


def merge(base: dict, rel: str) -> tuple[bool, str]:
    """3-way merge live/base/staged. Writes the live file only on a clean merge;
    otherwise writes the conflict-marked result to data/staging/conflicts/<rel>."""
    b = base_blob(base, rel)
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(git("cat-file", "blob", b).stdout)
        base_tmp = tf.name
    try:
        r = git("merge-file", "-p", "-L", "live", "-L", "run-base", "-L", "staged",
                rel, base_tmp, str(STAGED / rel), check=False)
    finally:
        os.unlink(base_tmp)
    if r.returncode < 0 or r.returncode > 127:
        return False, f"git merge-file failed: {r.stderr.decode().strip()}"
    merged = r.stdout.decode()
    remaining = r.returncode
    if remaining:
        merged, remaining = resolve_computed_only(merged)
    if remaining == 0:
        (REPO_ROOT / rel).write_text(merged)
        return True, "merged cleanly" + (" (computed-field hunks → live side)" if r.returncode else "")
    out = REPO_ROOT / CONFLICT_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(merged)
    return False, f"{remaining} conflict hunk(s) — live file untouched; marked result at {CONFLICT_DIR / rel}"


def promote(base: dict | None, only: list[str] | None, allow_no_base: bool) -> list[dict]:
    if base is None and not allow_no_base:
        sys.exit("No data/staging/run-base.json — cannot verify staged files against concurrent "
                 "changes. Re-run scripts/six-eyes-run.sh, or pass --allow-no-base after diffing "
                 "every overwrite against HEAD by hand.")
    results = []
    for row in check(base):
        rel = row["path"]
        if only and rel not in only:
            continue
        if not row["conflict"]:
            dest = REPO_ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / STAGED / rel, dest)
            results.append({**row, "result": "promoted"})
        elif row["action"] == "CONFLICT-merge":
            ok, msg = merge(base, rel)
            results.append({**row, "result": msg, "needs_mark": not ok})
        else:
            results.append({**row, "result": "SKIPPED — live file untouched", "needs_mark": True})
    return results


# --------------------------------------------------------------------------- cli


def print_table(rows: list[dict], with_result: bool) -> None:
    head = "| Staged file | → Final path | Action |" + (" Result |" if with_result else " Why |")
    print(head)
    print("|---|---|---|---|")
    for r in rows:
        last = r.get("result", "") if with_result else r["reason"]
        print(f"| {STAGED / r['path']} | {r['path']} | {r['action']} | {last} |")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record-base")
    c = sub.add_parser("check")
    c.add_argument("--json", action="store_true")
    p = sub.add_parser("promote")
    p.add_argument("--only", nargs="+", help="promote just these final paths (subset approval)")
    p.add_argument("--allow-no-base", action="store_true",
                   help="legacy blind copy when run-base.json is missing (diff by hand first)")
    p.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "record-base":
        b = record_base()
        print(f"Recorded run base: HEAD {b['head'][:10]}, {len(b['dirty'])} dirty/untracked file(s) snapshotted.")
        return 0

    base = load_base()
    if args.cmd == "check":
        rows = check(base)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            if base is None:
                print("⚠️  No run-base.json — conflict detection unavailable; overwrites are unverified.\n")
            print_table(rows, with_result=False)
            conflicts = [r for r in rows if r["conflict"]]
            print(f"\n{len(rows)} staged file(s), {len(conflicts)} CONFLICT(s).")
        return 2 if (base is None or any(r["conflict"] for r in rows)) else 0

    rows = promote(base, args.only, args.allow_no_base)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows, with_result=True)
        flagged = [r for r in rows if r.get("needs_mark")]
        print(f"\n{len(rows)} file(s) processed, {len(flagged)} need the operator's attention.")
    return 2 if any(r.get("needs_mark") for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
