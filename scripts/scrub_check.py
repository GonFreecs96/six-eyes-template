#!/usr/bin/env python3
"""scrub_check.py — the deny-token gate for this public template.

six-eyes-template is the scrubbed, fictional-data form of a private analytics
workspace. The skills, scoring code and orchestration were ported across; the
original's module prefixes, connector ids, contact addresses and internal doc
paths were not. This script is the mechanical check that they stay out: it
walks every tracked file, matches a deny list case-insensitively, prints each
hit as `path:line:token`, and exits non-zero if there is even one.

Run it before every commit (scripts/hooks/pre-commit does); the tests suite
(tests/test_scrub_check.py) and .github/workflows/tests.yml run it on every push:

    python3 scripts/scrub_check.py          # report hits, exit 1 if any
    python3 scripts/scrub_check.py --quiet  # exit code only

Standard library only, so it runs anywhere Python 3.9+ does with no install.
Pattern borrowed from kattfot's scripts/scrub_check.py.

Two deliberate limitations, documented rather than papered over:

  - **This file is exempt from its own scan.** It necessarily spells every
    token out. Nothing else is exempt, so a leak anywhere in the tree fails.
  - **Matching is line-by-line.** A token split across a line break is not
    caught. Tokens are short and prose wraps between words, so this is a
    reasonable trade for output that can name a line number.

The tokens are a blocklist, not a sandbox: it catches the known-bad names, not
every way to describe a private system. Human review of new prose is still the
durable control. When a scrub pass removes something, add its token here.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# This file is the one place the tokens are written out in full, so it cannot
# scan itself. Paths are repo-relative, POSIX-style.
SELF_EXEMPT = {"scripts/scrub_check.py"}

# Directories never worth walking in the filesystem-fallback mode (the
# git-tracked path already excludes them via .gitignore).
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", "node_modules",
             "outputs", "metadata"}

# Every pattern is matched case-insensitively against each line. Grouped by
# what it protects against, so a reviewer adding a token knows where it goes.
DENY_TOKENS: tuple[str, ...] = (
    # Company / repo names of the private original.
    r"bestow",
    r"\bBEAR\b",
    r"bear_[a-z]",
    r"6-eyes",
    # Backlog item-ID prefixes of the private original. The template's are
    # ONB/CHK/BIL/LIF/PLT (config/modules.json); the left-boundary guard keeps
    # e.g. "ACMEPLT-90" and "SDK DT-" style prose from false-matching.
    r"ACO\|APP\|CO",
    r"(?<![A-Za-z0-9])ACO-\d",
    r"(?<![A-Za-z0-9])APP-\d",
    r"(?<![A-Za-z0-9])PRE-\d",
    r"(?<![A-Za-z0-9])AH-\d",
    r"(?<![A-Za-z0-9])DT-\d",
    # Pre-scrub module label that lingered in dashboard_helpers.py.
    r"app-checkout",
    r"App & Checkout",
    # Connector instance ids that were hard-coded in agent-pipeline-run.sh.
    r"895f69c7-ac57-481d-983c-2083485b3062",
    r"20369ed0-bc95-447b-9156-a036637c58d0",
    # Internal docs that are not in the template.
    r"docs/contacts\.md",
    r"docs/archive/strategy",
    r"ARCHITECTURE\s*§",
    r"§\s*\d",
    # Contact addresses: any email whose domain is not an example.* domain.
    r"[A-Za-z0-9._%+-]+@(?![A-Za-z0-9.-]*example\.)[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    # Atlassian sites other than the two placeholder hosts.
    r"(?<![a-z0-9-])(?!example\.|your-org\.)[a-z0-9-]+\.atlassian\.net",
)

_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (token, re.compile(token, re.IGNORECASE)) for token in DENY_TOKENS
)


class Hit:
    """One deny-token match: where it is, and which token fired."""

    __slots__ = ("path", "line", "token", "text")

    def __init__(self, path: str, line: int, token: str, text: str):
        self.path, self.line, self.token, self.text = path, line, token, text

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.token}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Hit({self!s})"


def scan_text(text: str, path: str = "<text>") -> list[Hit]:
    """Every deny-token hit in `text`, in file order then deny-list order."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for token, rx in _COMPILED:
            if rx.search(line):
                hits.append(Hit(path, lineno, token, line.strip()))
    return hits


def scan_file(path: Path, *, rel: str | None = None) -> list[Hit]:
    """Scan one file. Unreadable or non-UTF-8 (binary) files yield no hits."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(text, rel or path.name)


def tracked_files(root: Path) -> list[Path]:
    """Git-tracked files, or a filesystem walk when git can't answer.

    Before the first `git add` `git ls-files` is empty, which would make the
    gate pass vacuously. Falling back to a walk keeps it usable as the very
    first check on a new repo.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode == 0:
            names = [n for n in out.stdout.split("\0") if n]
            if names:
                return [root / n for n in names]
    except (OSError, subprocess.SubprocessError):
        pass

    found = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        found.append(p)
    return found


def scan_repo(root: Path | None = None) -> list[Hit]:
    """Scan every tracked file under `root`, skipping this script itself."""
    root = root or REPO_ROOT
    hits = []
    for path in tracked_files(root):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        if rel in SELF_EXEMPT or not path.is_file():
            continue
        hits.extend(scan_file(path, rel=rel))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=None, help="repo root to scan (default: this repo)")
    ap.add_argument("--quiet", action="store_true", help="suppress output; exit code only")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else REPO_ROOT
    hits = scan_repo(root)

    if not args.quiet:
        for hit in hits:
            print(hit)
        sys.stdout.flush()
        n_files = len({h.path for h in hits})
        if hits:
            print(
                f"\nFAIL: {len(hits)} deny-token hit(s) in {n_files} file(s). "
                f"Scrub them before committing.",
                file=sys.stderr,
            )
        else:
            print(f"CLEAN: no deny tokens found ({len(DENY_TOKENS)} tokens checked).")

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
