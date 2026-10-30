#!/usr/bin/env python3
"""
Reconcile backlog frontmatter dates against each item's ## Notes body.

`last_progress` drives stale_weeks -> escalation_level, but it is hand-maintained
and drifts when Notes gain dated progress entries that frontmatter never picked up.
Reactivated items can read as long-idle zombies to every downstream consumer.

Extraction is deterministic on purpose. Freeform LLM estimates of `stale_weeks`
fight `sync-metadata.py`'s authoritative recompute; date extraction by judgment
would reintroduce that failure. This script decides; the skill reviews what it defers.

Usage:
    python3 scripts/reconcile-progress-dates.py            # dry-run report
    python3 scripts/reconcile-progress-dates.py --apply    # write unambiguous only
    python3 scripts/reconcile-progress-dates.py --json     # machine-readable

Never touches computed fields (stale_weeks, escalation_level, priority_score) --
those stay sync-metadata.py's. Run sync-metadata.py after --apply so they
recompute from the corrected dates.
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BACKLOG_DIR = REPO_ROOT / "data" / "backlog"

IN_SCOPE_STATUSES = {"active", "waiting", "monitoring"}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)

# Entry-heading dates we trust for auto-apply: a full ISO date in heading
# position at the start of a line, optionally bolded or as a markdown heading,
# followed by a separator.
# Matches:  **2026-09-01 - ...**   |   **2026-09-01**   |   2026-09-01 - ...
#           ### 2026-09-01 — ...  (pulse-scan's entry style; always review-only
#           for last_progress — e.g. LIF-007 / ONB-010 / CHK-004 may need manual review)
STRICT_HEADING_RE = re.compile(
    r"^\s*(?:#{2,6}\s+)?(?:\*\*)?(\d{4}-\d{2}-\d{2})(?:\*\*)?\s*(?:[-–—:]|\*\*|$)",
    re.MULTILINE,
)

# The markdown-heading subset of the above. pulse-scan writes one of these every
# time it *mentions* an item ("### 2026-10-05 — Pulse ... — no new signal"), so the
# date proves a touch, not progress: it may auto-set last_touched, but a
# last_progress bump from it always goes to review.
MD_HEADING_RE = re.compile(
    r"^\s*#{2,6}\s+(?:\*\*)?(\d{4}-\d{2}-\d{2})(?:\*\*)?\s*(?:[-–—:]|\*\*|$)",
    re.MULTILINE,
)

# Heading-position dates we do NOT trust: month-name form with no year
# (e.g. "**Jun 15 (created):**"). Reported for review, never auto-applied.
# Anchored to real month names -- an earlier draft used a generic [A-Z][a-z]+
# and matched headings like "**Trigger 3**" as dates.
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LOOSE_HEADING_RE = re.compile(
    r"^\s*\*\*((?:" + "|".join(MONTHS) + r")[a-z]*\.?\s+\d{1,2})\b",
    re.MULTILINE,
)

# Any ISO date anywhere, used only to detect prose-only references.
ANY_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# An entry that explicitly records "nothing changed" is an annotation, not
# progress. Bumping last_progress on these would reset the staleness clock for
# an item that genuinely did not move, which is the opposite of the point.
NO_CHANGE_MARKERS = (
    "no change", "no update", "still blocked", "unchanged", "no movement",
    "no progress", "nothing new", "no new", "still waiting", "still open",
    "no signal", "context only",
)


def split_frontmatter(content: str):
    m = FRONTMATTER_RE.match(content)
    if not m:
        return None, content
    return m.group(1), m.group(2)


def fm_get(frontmatter_str: str, key: str):
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", frontmatter_str, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'") or None


def set_frontmatter_field(frontmatter_str: str, key: str, value) -> str:
    """Replace an existing key's value, or append the key if missing.

    Mirrors sync-metadata.py's helper so both writers format identically.
    """
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    new_line = f"{key}: {value}"
    if pattern.search(frontmatter_str):
        return pattern.sub(new_line, frontmatter_str, count=1)
    return frontmatter_str.rstrip("\n") + "\n" + new_line


def notes_section(body: str) -> str:
    """Everything from the '## Notes' heading onward; '' if there is none."""
    m = re.search(r"^##\s+Notes\s*$", body, re.MULTILINE)
    return body[m.end():] if m else ""


def entry_text_for(notes: str, iso: str) -> str:
    """The line the given heading date appears on, trimmed for reporting."""
    for line in notes.splitlines():
        if iso in line and STRICT_HEADING_RE.match(line):
            return line.strip()[:160]
    return ""


def looks_like_no_change(entry: str) -> bool:
    low = entry.lower()
    return any(marker in low for marker in NO_CHANGE_MARKERS)


def parse_iso(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def analyze(path: Path):
    """Return a finding dict for one backlog file, or None if out of scope."""
    content = path.read_text()
    fm, body = split_frontmatter(content)
    if fm is None:
        return None

    status = (fm_get(fm, "status") or "").lower()
    if status not in IN_SCOPE_STATUSES:
        return None

    item_id = fm_get(fm, "id") or path.stem
    lp = parse_iso(fm_get(fm, "last_progress"))
    lt = parse_iso(fm_get(fm, "last_touched"))
    notes = notes_section(body)

    finding = {
        "id": item_id,
        "path": str(path.relative_to(REPO_ROOT)),
        "status": status,
        "last_progress": lp.isoformat() if lp else None,
        "last_touched": lt.isoformat() if lt else None,
        "newest_entry": None,
        "entry_text": "",
        "action": "none",
        "reason": "",
    }

    if not notes.strip():
        finding.update(action="review", reason="no ## Notes section")
        return finding

    strict = sorted({d for d in STRICT_HEADING_RE.findall(notes)})
    loose = LOOSE_HEADING_RE.findall(notes)

    if not strict:
        # No trustworthy heading date. Only surface this for review when there is
        # actual evidence the frontmatter is behind -- otherwise every item with
        # month-name headings would be flagged forever, drowning the real cases.
        prose_dates = sorted({d for d in ANY_ISO_RE.findall(notes) if parse_iso(d)})
        newest_prose = parse_iso(prose_dates[-1]) if prose_dates else None
        behind = lp is None or (newest_prose and newest_prose > lp)

        if not behind:
            finding.update(reason="no ISO entry headings; frontmatter not behind any date in Notes")
        elif loose:
            finding.update(
                action="review",
                reason=(f"only non-ISO entry headings (e.g. '{loose[-1]}') — year must be "
                        f"inferred; newest date seen in Notes is "
                        f"{prose_dates[-1] if prose_dates else 'none'}"),
            )
        elif newest_prose:
            finding.update(
                action="review",
                reason=f"dates appear only in prose (newest {prose_dates[-1]}), no entry heading",
            )
        else:
            finding.update(action="review", reason="last_progress is unset and Notes carries no date")
        return finding

    newest = max(strict)
    newest_d = parse_iso(newest)
    finding["newest_entry"] = newest
    entry = entry_text_for(notes, newest)
    finding["entry_text"] = entry

    if newest_d and newest_d > date.today():
        finding.update(action="review", reason=f"entry date {newest} is in the future")
        return finding

    # A loose heading newer than the newest strict one means the real latest
    # entry may be the undated-year one — defer rather than guess. Only when
    # Notes carries some date newer than last_progress, though: otherwise old
    # month-name headings on a current item (e.g. BIL-005, ONB-010) flag forever.
    if loose and lp and newest_d and newest_d <= lp:
        prose_dates = [d for d in (parse_iso(x) for x in ANY_ISO_RE.findall(notes)) if d]
        if prose_dates and max(prose_dates) > lp:
            finding.update(action="review",
                           reason=(f"non-ISO entry headings present, no ISO entry is newer, "
                                   f"but Notes mentions {max(prose_dates).isoformat()}"))
        else:
            finding["reason"] = "frontmatter not behind any date in Notes"
        return finding

    needs_lp = lp is None or (newest_d and newest_d > lp)
    needs_lt = lt is None or (newest_d and newest_d > lt)

    if not needs_lp and not needs_lt:
        finding["reason"] = "frontmatter already current"
        return finding

    md_dates = set(MD_HEADING_RE.findall(notes))
    bold_dates = {d for d in strict if d not in md_dates}
    if needs_lp and newest in md_dates and newest not in bold_dates:
        if not needs_lt:
            # The writer already recorded the touch and chose not to claim
            # progress — that decision was made at write time; don't re-ask it.
            finding["reason"] = "'###' entry already reflected in last_touched; progress not claimed"
            return finding
        # Frontmatter wasn't maintained at all: touch is certain, progress is not.
        finding.update(
            action="apply",
            reason="newest entry is a '###' pulse-style heading — last_touched applied, "
                   "last_progress needs confirmation",
            set_last_progress=None,
            set_last_touched=newest,
            review_last_progress=newest,
        )
        return finding

    if needs_lp and looks_like_no_change(entry):
        # Touch the file date, but do not reset the progress clock.
        finding.update(
            action="review",
            reason="newest entry reads as a no-change annotation — confirm before bumping last_progress",
        )
        return finding

    finding.update(
        action="apply",
        reason="ISO entry heading newer than frontmatter",
        set_last_progress=newest if needs_lp else None,
        set_last_touched=newest if needs_lt else None,
    )
    return finding


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the unambiguous corrections (action=apply)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    findings = []
    for path in sorted(BACKLOG_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        f = analyze(path)
        if f and (f["action"] != "none" or f.get("newest_entry")):
            findings.append(f)

    to_apply = [f for f in findings if f["action"] == "apply"]
    # A touch-only apply still owes a progress decision, so it is listed in both.
    to_review = [f for f in findings
                 if f["action"] == "review" or f.get("review_last_progress")]

    if args.apply:
        for f in to_apply:
            path = REPO_ROOT / f["path"]
            content = path.read_text()
            fm, body = split_frontmatter(content)
            if f.get("set_last_progress"):
                fm = set_frontmatter_field(fm, "last_progress", f["set_last_progress"])
            if f.get("set_last_touched"):
                fm = set_frontmatter_field(fm, "last_touched", f["set_last_touched"])
            path.write_text(f"---\n{fm}\n---\n{body}")

    if args.json:
        print(json.dumps({"applied" if args.apply else "unambiguous": to_apply,
                          "review": to_review}, indent=2))
        return 0

    verb = "Applied" if args.apply else "Unambiguous (run with --apply to write)"
    print(f"=== {verb}: {len(to_apply)} ===")
    for f in to_apply:
        bits = []
        if f.get("set_last_progress"):
            bits.append(f"last_progress {f['last_progress']} -> {f['set_last_progress']}")
        if f.get("set_last_touched"):
            bits.append(f"last_touched {f['last_touched']} -> {f['set_last_touched']}")
        print(f"  {f['id']:9} {'; '.join(bits)}")
        if f["entry_text"]:
            print(f"            entry: {f['entry_text']}")

    print(f"\n=== Needs review: {len(to_review)} ===")
    for f in to_review:
        print(f"  {f['id']:9} [{f['status']}] last_progress={f['last_progress']} — {f['reason']}")
        if f["entry_text"]:
            print(f"            entry: {f['entry_text']}")

    if args.apply and to_apply:
        print("\nRe-run `python3 scripts/sync-metadata.py` so stale_weeks/escalation_level recompute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
