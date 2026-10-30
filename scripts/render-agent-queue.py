#!/usr/bin/env python3
"""
render-agent-queue.py - deterministic renderer for the agent work queue.

Reads agent-step frontmatter straight from data/backlog/*.md (the same fields
sync-metadata.py indexes) and renders:

  - Investigate   agent_step_type=investigate, priority_score DESC
  - Checks due    agent_step_type=check AND agent_step_as_of <= today - recheck days
  - Checks waiting  agent_step_type=check, not yet due (shows the next due date)
  - counts        investigate / checks_due / checks_waiting / no_step / unassessed / invalid

Excludes status done and backburner. Step semantics, recheck_after_days and the
field names come from config/agent-workability.json via dashboard_helpers.

Usage:
  python3 scripts/render-agent-queue.py                       # writes outputs/agent-work-queue.md
  python3 scripts/render-agent-queue.py --out PATH            # write markdown elsewhere
  python3 scripts/render-agent-queue.py --json                # JSON to stdout, writes nothing
  python3 scripts/render-agent-queue.py --overlay DIR         # DIR's files win over live ones (staging)
  python3 scripts/render-agent-queue.py --today YYYY-MM-DD    # override "today" (tests)

Exit 0 on success. Invalid arguments (including a malformed --today) exit 2. Unparsable backlog
files are skipped with a WARN on stderr. A missing --overlay directory is a WARN and the overlay
is treated as empty.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from dashboard_helpers import (  # noqa: E402
    RECHECK_AFTER_DAYS,
    agent_step_state,
    normalize_step_field,
)

REPO = Path(__file__).parent.parent
BACKLOG = REPO / "data" / "backlog"
DEFAULT_OUT = REPO / "outputs" / "agent-work-queue.md"
EXCLUDED_STATUSES = {"done", "backburner"}
ID_RE = re.compile(r"^([A-Z]+-\d+)")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TITLE_MAX = 70


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader without the timestamp resolver: dates stay strings, so an impossible
    date (2026-02-30) reaches agent_step_state as 'invalid' instead of breaking the parse."""


_StringDateLoader.yaml_implicit_resolvers = {
    key: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def warn(msg: str):
    print(f"WARN: {msg}", file=sys.stderr)


def read_item(path: Path):
    """Return (frontmatter dict) or None if the file is unparsable / has no id."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        warn(f"[{path.name}]: unreadable ({e}), skipped")
        return None
    m = FM_RE.match(text)
    if not m:
        warn(f"[{path.name}]: no frontmatter, skipped")
        return None
    try:
        fm = yaml.load(m.group(1), Loader=_StringDateLoader) or {}
    except (yaml.YAMLError, ValueError) as e:
        warn(f"[{path.name}]: YAML parse error, skipped ({e})")
        return None
    if not isinstance(fm, dict):
        warn(f"[{path.name}]: frontmatter is not a mapping, skipped")
        return None
    if not fm.get("id"):
        m_id = ID_RE.match(path.name)
        if not m_id:
            warn(f"[{path.name}]: no id field, skipped")
            return None
        fm["id"] = m_id.group(1)
    fm["id"] = str(fm["id"]).strip()
    return fm


def load_items(overlay: Path | None):
    """Live backlog keyed by id, with overlay files replacing same-id entries."""
    items = {}
    for path in sorted(BACKLOG.glob("*.md")):
        if path.name.startswith("_"):
            continue
        fm = read_item(path)
        if fm is not None:
            items[fm["id"]] = fm
    if overlay is not None and not overlay.is_dir():
        warn(f"--overlay directory not found, treated as empty: {overlay}")
    elif overlay is not None:
        for path in sorted(overlay.glob("*.md")):
            if path.name.startswith("_"):
                continue
            fm = read_item(path)
            if fm is not None:
                items[fm["id"]] = fm  # staged full file wins
    return items


def score_of(fm) -> float:
    try:
        return float(fm.get("priority_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def squash(text, n=TITLE_MAX) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def build(items: dict, today: date):
    investigate, checks_due, checks_waiting = [], [], []
    counts = {"investigate": 0, "checks_due": 0, "checks_waiting": 0,
              "no_step": 0, "unassessed": 0, "invalid": 0}

    for fm in items.values():
        if normalize_step_field(fm.get("status"), lower=True) in EXCLUDED_STATUSES:
            continue
        st = agent_step_state(fm)
        state = st["state"]
        row = {
            "id": fm["id"],
            "title": squash(fm.get("title")),
            "module": normalize_step_field(fm.get("module")) or "—",
            "score": round(score_of(fm), 1),
            "step": st["step"],
            "check": st["check"],
            "as_of": st["as_of"],
        }
        if state == "investigate":
            investigate.append(row)
            counts["investigate"] += 1
        elif state == "check":
            as_of = date.fromisoformat(st["as_of"])
            if as_of <= today - timedelta(days=RECHECK_AFTER_DAYS):
                checks_due.append(row)
                counts["checks_due"] += 1
            else:
                row["next_due"] = (as_of + timedelta(days=RECHECK_AFTER_DAYS)).isoformat()
                checks_waiting.append(row)
                counts["checks_waiting"] += 1
        elif state == "none":
            counts["no_step"] += 1
        elif state == "unassessed":
            counts["unassessed"] += 1
        elif state == "invalid":
            counts["invalid"] += 1

    investigate.sort(key=lambda r: (-r["score"], r["id"]))
    checks_due.sort(key=lambda r: (r["as_of"], r["id"]))
    checks_waiting.sort(key=lambda r: (r["next_due"], r["id"]))
    return investigate, checks_due, checks_waiting, counts


def md_cell(s) -> str:
    if s is None or s == "":
        return "—"
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(today: date, investigate, checks_due, checks_waiting, counts) -> str:
    out = [
        f"# Agent Work Queue — {today.isoformat()}",
        "",
        "Run `/agent-work` to pick, `/agent-work [id]` to run one, `/agent-work --checks` for due checks. "
        "Steps set by /agent-triage and /agent-work; rubric in config/agent-workability.json.",
        "",
        "## Investigate",
        "",
    ]
    if investigate:
        out += ["| Item | Title | Module | Score | Next step | Check |",
                "|------|-------|--------|-------|-----------|-------|"]
        for r in investigate:
            out.append(f"| {r['id']} | {md_cell(r['title'])} | {md_cell(r['module'])} | {r['score']:g} | "
                       f"{md_cell(r['step'])} | {md_cell(r['check'])} |")
    else:
        out.append("_No investigate steps queued._")
    out += ["", "## Checks due", ""]
    if checks_due:
        out += ["| Item | Title | Check step | As of | Check |",
                "|------|-------|------------|-------|-------|"]
        for r in checks_due:
            out.append(f"| {r['id']} | {md_cell(r['title'])} | {md_cell(r['step'])} | {r['as_of']} | "
                       f"{md_cell(r['check'])} |")
    else:
        out.append("_No checks due._")
    out += ["", "## Checks waiting", ""]
    if checks_waiting:
        out += ["| Item | Title | Check step | Next due |",
                "|------|-------|------------|----------|"]
        for r in checks_waiting:
            out.append(f"| {r['id']} | {md_cell(r['title'])} | {md_cell(r['step'])} | {r['next_due']} |")
    else:
        out.append("_No checks waiting._")
    out += [
        "",
        "## Summary",
        "",
        f"{counts['investigate']} investigate · {counts['checks_due']} checks due · "
        f"{counts['checks_waiting']} checks waiting · {counts['no_step']} with no step · "
        f"{counts['unassessed']} unassessed · {counts['invalid']} invalid step fields.",
        "",
    ]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="markdown output path")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout; write nothing")
    ap.add_argument("--overlay", type=Path, default=None,
                    help="directory of backlog files that take precedence over live ones (staging)")
    ap.add_argument("--today", type=str, default=None, help="YYYY-MM-DD override for today (tests)")
    args = ap.parse_args()

    if args.today is not None:
        try:
            today = datetime.strptime(args.today, "%Y-%m-%d").date()
        except ValueError:
            ap.error(f"--today must be YYYY-MM-DD, got {args.today!r}")
    else:
        today = date.today()

    items = load_items(args.overlay)
    investigate, checks_due, checks_waiting, counts = build(items, today)

    if args.json:
        payload = {
            "generated": today.isoformat(),
            "investigate": investigate,
            "checks_due": checks_due,
            "checks_waiting": checks_waiting,
            "counts": counts,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    md = render_markdown(today, investigate, checks_due, checks_waiting, counts)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md, encoding="utf-8")
    print(f"Wrote {args.out} ({counts['investigate']} investigate, {counts['checks_due']} checks due, "
          f"{counts['checks_waiting']} waiting)")


if __name__ == "__main__":
    main()
