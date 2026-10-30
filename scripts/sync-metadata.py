#!/usr/bin/env python3
"""
Sync YAML frontmatter from data/backlog/*.md into metadata/sixeyes.db.

Computes derived fields (priority_score, stale_weeks, escalation_level) and
writes them back to the markdown frontmatter. Rebuilds the FTS5 index.
Snapshots score history per item per day and rebuilds pulse_mentions from
data/pulse-checks/ files.
"""

import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from dashboard_helpers import (
    ITEM_ID_RE, is_bad_step_value, normalize_step_field, parse_as_of,
)

try:
    import yaml
except ImportError:
    print("pyyaml not found. Run: pip install pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent
DB_PATH = REPO_ROOT / "metadata" / "sixeyes.db"
BACKLOG_DIR = REPO_ROOT / "data" / "backlog"
WEIGHTS_PATH = REPO_ROOT / "config" / "scoring-weights.json"


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

def load_weights():
    with open(WEIGHTS_PATH) as f:
        cfg = json.load(f)
    w = cfg["weights"]
    # config/scoring-weights.json is the single source for thresholds; no code
    # defaults, so a missing key fails loudly instead of drifting from the docs.
    t = cfg["staleness_thresholds"]
    return (w["business_impact"], w["time_sensitivity"], w["data_readiness"],
            t["flag_weeks"], t["escalate_weeks"], t["stale_mention_threshold"])


# ---------------------------------------------------------------------------
# Frontmatter parsing and writing
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def split_frontmatter(content: str):
    """Return (frontmatter_str, body_str) or (None, content) if no frontmatter."""
    m = FRONTMATTER_RE.match(content)
    if not m:
        return None, content
    return m.group(1), m.group(2)


def parse_frontmatter(frontmatter_str: str, source: str = ""):
    try:
        return yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError as e:
        print(f"WARN [{source}]: YAML parse error, file skipped: {e}", file=sys.stderr)
        return {}


def set_frontmatter_field(frontmatter_str: str, key: str, value) -> str:
    """Replace the value of an existing key, or append it if missing."""
    # Format the value for YAML
    if value is None:
        yaml_value = "null"
    elif isinstance(value, float):
        yaml_value = f"{value:.2f}"
    else:
        yaml_value = str(value)

    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    new_line = f"{key}: {yaml_value}"
    if pattern.search(frontmatter_str):
        return pattern.sub(new_line, frontmatter_str)
    else:
        return frontmatter_str.rstrip() + f"\n{new_line}"


def rebuild_file(frontmatter_str: str, body: str) -> str:
    return f"---\n{frontmatter_str}\n---\n{body}"


# ---------------------------------------------------------------------------
# Derived field computation
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = {"backburner", "done"}


ACTIVE_WEEKS_CACHE = None


def system_active_weeks():
    """ISO (year, week) pairs in which Six Eyes actually ran.

    A week counts as active if it produced a pulse-check file. `stale_weeks` is
    measured in these weeks, not calendar weeks, so an operator absence does not
    age the whole backlog in lockstep — without this, a long idle gap can push
    many items over escalation thresholds the day pulses resume.
    """
    global ACTIVE_WEEKS_CACHE
    if ACTIVE_WEEKS_CACHE is None:
        weeks = set()
        pulse_dir = REPO_ROOT / "data" / "pulse-checks"
        if pulse_dir.is_dir():
            for path in pulse_dir.glob("*.md"):
                m = re.match(r"(\d{4})-W(\d{2})", path.name)
                if m:
                    weeks.add((int(m.group(1)), int(m.group(2))))
        ACTIVE_WEEKS_CACHE = weeks
    return ACTIVE_WEEKS_CACHE


def active_weeks_since(start: date, today: date, active=None) -> int:
    """Count system-active weeks strictly after `start`, up to `today`.

    `active` defaults to the pulse-check archive (system_active_weeks()); tests
    pass an explicit set. Falls back to plain calendar weeks if no pulse-check
    archive is present, so a fresh clone or a wiped data/pulse-checks/ still
    produces sane staleness.
    """
    if active is None:
        active = system_active_weeks()
    if not active:
        return (today - start).days // 7
    n, cur = 0, start
    while True:
        cur += timedelta(days=7)
        if cur > today:
            return n
        iso_year, iso_week, _ = cur.isocalendar()
        if (iso_year, iso_week) in active:
            n += 1


def compute_fields(data: dict, w_bi: float, w_ts: float, w_dr: float,
                   flag_weeks: int, escalate_weeks: int,
                   stale_mention_threshold: int, today: date = None,
                   active_weeks=None):
    """Return (priority_score, stale_weeks, escalation_level) for one item.

    `today` and `active_weeks` exist for tests; production callers omit both.
    """
    if today is None:
        today = date.today()

    # stale_weeks from last_progress, counted in system-active weeks
    raw_lp = data.get("last_progress")
    try:
        lp = date.fromisoformat(str(raw_lp)) if raw_lp else today
    except ValueError:
        lp = today
    stale_weeks = active_weeks_since(lp, today, active_weeks)

    # priority_score
    bi = int(data.get("business_impact") or 0)
    ts = int(data.get("time_sensitivity") or 0)
    dr = int(data.get("data_readiness") or 0)
    priority_score = round((bi * w_bi + ts * w_ts + dr * w_dr) * 20, 2)

    # escalation_level — thresholds come from config/scoring-weights.json
    mention_count = int(data.get("mention_count") or 0)
    progress_count = int(data.get("progress_count") or 0)
    mention_gap = mention_count - progress_count

    if stale_weeks >= escalate_weeks:
        escalation_level = 2
    elif stale_weeks >= flag_weeks:
        escalation_level = 1
    else:
        escalation_level = 0

    # Mention-gap is accumulated history (not a snapshot), so it stands on its own:
    # a high-attention item escalates regardless of score. score > 60 promotes it to
    # level 2; otherwise it flags at level 1 for high-attention stale items.
    # The gap is lifetime, so it only applies once the item is itself flag-stale —
    # otherwise an item that progressed this week stays escalated forever.
    if mention_gap >= stale_mention_threshold and stale_weeks >= flag_weeks:
        escalation_level = max(escalation_level, 2 if priority_score > 60 else 1)

    # Closed/resolved/backburner/completed items are done — staleness and mention-gap
    # accrue on the calendar even after an item stops moving, so without this a
    # closed item would silently escalate again on every sync and keep resurfacing
    # as an escalation candidate.
    status = str(data.get("status") or "").strip().lower()
    if status in TERMINAL_STATUSES:
        escalation_level = 0

    return priority_score, stale_weeks, escalation_level


# ---------------------------------------------------------------------------
# Schema migration (idempotent — keeps an existing DB in sync with init-db.py)
# ---------------------------------------------------------------------------

STEP_FIELDS = ["agent_next_step", "agent_step_type", "agent_step_check", "agent_step_as_of"]
VALID_STEP_TYPES = {"investigate", "check"}


def ensure_schema(conn: sqlite3.Connection):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    for col in STEP_FIELDS:
        if col not in cols:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")

    # Retired item-level label (replaced by STEP_FIELDS, 2026-10). DROP COLUMN needs
    # SQLite >= 3.35; on older builds leave it in place — upsert no longer reads it.
    if "agent_workability" in cols:
        try:
            conn.execute("ALTER TABLE items DROP COLUMN agent_workability")
        except sqlite3.OperationalError as e:
            print(f"  note: could not drop legacy agent_workability column ({e})")
    conn.commit()

    # Create score_history table if it doesn't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS score_history (
            item_id          TEXT,
            snapshot_date    TEXT,
            priority_score   REAL,
            business_impact  INTEGER,
            time_sensitivity INTEGER,
            data_readiness   INTEGER,
            stale_weeks      INTEGER,
            escalation_level INTEGER,
            status           TEXT,
            PRIMARY KEY (item_id, snapshot_date)
        )
    """)

    # Add source_file column to pulse_mentions if missing
    pm_cols = {row[1] for row in conn.execute("PRAGMA table_info(pulse_mentions)")}
    if "source_file" not in pm_cols:
        conn.execute("ALTER TABLE pulse_mentions ADD COLUMN source_file TEXT")

    # Create dedup view for pulse_mentions (handles duplicate rows from sibling pulse files)
    conn.execute("""
        CREATE VIEW IF NOT EXISTS pulse_mentions_weekly AS
        SELECT item_id, pulse_date, MAX(had_progress) AS had_progress, COUNT(*) AS n_sources
        FROM pulse_mentions
        GROUP BY item_id, pulse_date
    """)

    conn.commit()


# ---------------------------------------------------------------------------
# Agent step fields (config/agent-workability.json)
# ---------------------------------------------------------------------------

def normalized_step_fields(item_id: str, data: dict) -> dict:
    """Normalize the four agent_step_* values (shared rules in dashboard_helpers).
    Prints WARN for YAML non-scalar values and malformed as_of dates; never raises."""
    for key in STEP_FIELDS:
        if is_bad_step_value(data.get(key)):
            print(f"WARN [{item_id}]: {key} is a YAML {type(data.get(key)).__name__}, not a scalar; stored as null",
                  file=sys.stderr)
    as_of, as_of_ok = parse_as_of(data.get("agent_step_as_of"))
    if not as_of_ok:
        print(f"WARN [{item_id}]: agent_step_as_of '{as_of}' is not YYYY-MM-DD", file=sys.stderr)
    return {
        "agent_next_step": normalize_step_field(data.get("agent_next_step")),
        "agent_step_type": normalize_step_field(data.get("agent_step_type"), lower=True),
        "agent_step_check": normalize_step_field(data.get("agent_step_check")),
        "agent_step_as_of": as_of,
    }


def validate_step_fields(item_id: str, step: dict):
    """Print WARN lines for inconsistent agent step fields. Never raises or changes exit code."""
    def warn(msg):
        print(f"WARN [{item_id}]: {msg}", file=sys.stderr)

    has_step = step["agent_next_step"] is not None
    stype = step["agent_step_type"]
    check = step["agent_step_check"]
    as_of, as_of_ok = parse_as_of(step["agent_step_as_of"])

    if stype is not None and not has_step:
        warn("agent_step_type set but agent_next_step is null")
    if has_step and stype is None:
        warn("agent_next_step set but agent_step_type is null")
    if stype is not None and stype not in VALID_STEP_TYPES:
        warn(f"agent_step_type {stype!r} not in investigate | check | null")
    if check is not None and not has_step:
        warn("agent_step_check set while agent_next_step is null")
    if as_of_ok and as_of is not None and date.fromisoformat(as_of) > date.today():
        warn(f"agent_step_as_of {as_of} is later than today")


# ---------------------------------------------------------------------------
# SQLite upsert
# ---------------------------------------------------------------------------

def upsert_item(conn: sqlite3.Connection, data: dict,
                priority_score: float, stale_weeks: int, escalation_level: int,
                step: dict):
    cross_modules_raw = data.get("cross_modules") or []
    if isinstance(cross_modules_raw, str):
        cross_modules_raw = [cross_modules_raw]
    cross_modules_json = json.dumps(list(cross_modules_raw))

    conn.execute("""
        INSERT INTO items (
            id, title, module, cross_modules, status,
            business_impact, time_sensitivity, data_readiness,
            priority_score, created, last_touched, last_progress,
            mention_count, progress_count, stale_weeks,
            blocked_reason, escalation_level,
            agent_next_step, agent_step_type, agent_step_check, agent_step_as_of
        ) VALUES (
            :id, :title, :module, :cross_modules, :status,
            :business_impact, :time_sensitivity, :data_readiness,
            :priority_score, :created, :last_touched, :last_progress,
            :mention_count, :progress_count, :stale_weeks,
            :blocked_reason, :escalation_level,
            :agent_next_step, :agent_step_type, :agent_step_check, :agent_step_as_of
        )
        ON CONFLICT(id) DO UPDATE SET
            title            = excluded.title,
            module           = excluded.module,
            cross_modules    = excluded.cross_modules,
            status           = excluded.status,
            business_impact  = excluded.business_impact,
            time_sensitivity = excluded.time_sensitivity,
            data_readiness   = excluded.data_readiness,
            priority_score   = excluded.priority_score,
            created          = excluded.created,
            last_touched     = excluded.last_touched,
            last_progress    = excluded.last_progress,
            mention_count    = excluded.mention_count,
            progress_count   = excluded.progress_count,
            stale_weeks      = excluded.stale_weeks,
            blocked_reason   = excluded.blocked_reason,
            escalation_level = excluded.escalation_level,
            agent_next_step  = excluded.agent_next_step,
            agent_step_type  = excluded.agent_step_type,
            agent_step_check = excluded.agent_step_check,
            agent_step_as_of = excluded.agent_step_as_of
    """, {
        "id":               str(data.get("id") or ""),
        "title":            str(data.get("title") or ""),
        "module":           str(data.get("module") or ""),
        "cross_modules":    cross_modules_json,
        "status":           str(data.get("status") or ""),
        "business_impact":  int(data.get("business_impact") or 0),
        "time_sensitivity": int(data.get("time_sensitivity") or 0),
        "data_readiness":   int(data.get("data_readiness") or 0),
        "priority_score":   priority_score,
        "created":          str(data.get("created") or ""),
        "last_touched":     str(data.get("last_touched") or ""),
        "last_progress":    str(data.get("last_progress") or ""),
        "mention_count":    int(data.get("mention_count") or 0),
        "progress_count":   int(data.get("progress_count") or 0),
        "stale_weeks":      stale_weeks,
        "blocked_reason":   data.get("blocked_reason"),
        "escalation_level": escalation_level,
        "agent_next_step": step["agent_next_step"],
        "agent_step_type": step["agent_step_type"],
        "agent_step_check": step["agent_step_check"],
        "agent_step_as_of": step["agent_step_as_of"],
    })


# ---------------------------------------------------------------------------
# Score history snapshots
# ---------------------------------------------------------------------------

def snapshot_score_history(conn: sqlite3.Connection, item_id: str, data: dict,
                           priority_score: float, stale_weeks: int,
                           escalation_level: int):
    """Record a daily snapshot of item's score and dimensions."""
    business_impact = int(data.get("business_impact") or 0)
    time_sensitivity = int(data.get("time_sensitivity") or 0)
    data_readiness = int(data.get("data_readiness") or 0)
    status = str(data.get("status") or "")

    conn.execute("""
        INSERT OR REPLACE INTO score_history (
            item_id, snapshot_date, priority_score,
            business_impact, time_sensitivity, data_readiness,
            stale_weeks, escalation_level, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item_id, date.today().isoformat(), priority_score,
        business_impact, time_sensitivity, data_readiness,
        stale_weeks, escalation_level, status
    ))


# ---------------------------------------------------------------------------
# Pulse mentions population
# ---------------------------------------------------------------------------

def populate_pulse_mentions(conn: sqlite3.Connection):
    """Rebuild pulse_mentions table from data/pulse-checks/*.md files."""
    pulse_dir = REPO_ROOT / "data" / "pulse-checks"
    if not pulse_dir.exists():
        return (0, 0)

    # Full rebuild: delete and repopulate
    conn.execute("DELETE FROM pulse_mentions")

    files = sorted(pulse_dir.glob("*.md"))
    row_count = 0
    file_count = 0

    for path in files:
        # Parse filename: YYYY-WXX-pulse.md
        match = re.match(r"(\d{4})-W(\d{2})", path.name)
        if not match:
            continue

        year = int(match.group(1))
        week = int(match.group(2))
        try:
            pulse_date = date.fromisocalendar(year, week, 1).isoformat()
        except ValueError:
            continue

        # Read file and extract "## Backlog Updates" sections (the pulse-scan
        # skill's section name; see templates and data/pulse-checks/)
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")
        except Exception as e:
            print(f"  SKIP pulse {path.name} — {e}")
            continue

        # Find ALL sections matching the pattern (including variants like "(staged)")
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.strip().startswith("## Backlog Updates"):
                section_start = i + 1

                # Extract lines until the next ## or EOF
                section_lines = []
                for j in range(section_start, len(lines)):
                    if lines[j].startswith("## "):
                        break
                    section_lines.append(lines[j])

                # Parse bullet items and table rows from this section
                try:
                    row_count += _parse_pulse_section(
                        conn, section_lines, pulse_date, path.name
                    )
                except Exception as e:
                    # Skip just this section and keep scanning — do NOT `continue`,
                    # which would bypass the i += 1 below and spin forever on the
                    # same heading line.
                    print(f"  SKIP pulse {path.name} — {e}")

            i += 1

        file_count += 1

    return (row_count, file_count)


def _parse_pulse_section(conn: sqlite3.Connection, section_lines: list,
                         pulse_date: str, source_file: str) -> int:
    """Parse bullets and table rows in a pulse section. Returns row count."""
    row_count = 0
    arrow_pattern = re.compile(r"progress(?:_count)?[`\s]*(\d+)\s*(?:→|->)\s*(\d+)")

    # Pattern for bullet: - **[IDs]** ...
    bullet_pattern = re.compile(r"^- \*\*([^*]+)\*\*(.*)$")

    # Pattern for table row: | **[IDs]** | ...
    table_pattern = re.compile(r"^\| \*\*([^*]+)\*\*")

    for line in section_lines:
        # Try bullet pattern
        bullet_match = bullet_pattern.match(line)
        if bullet_match:
            bold_span = bullet_match.group(1)
            rest_of_line = bullet_match.group(2)
            full_line = bold_span + rest_of_line

            # Extract all item IDs from the bold span. ITEM_ID_RE is built from
            # config/modules.json id_prefix values, with a left-boundary guard so
            # a Jira key like ACMEONB-1103 cannot mint a phantom ONB-1103 row.
            item_ids = ITEM_ID_RE.findall(bold_span)

            for item_id in item_ids:
                had_progress = _detect_progress(full_line, arrow_pattern)
                context = _extract_context(rest_of_line)

                conn.execute("""
                    INSERT INTO pulse_mentions (item_id, pulse_date, had_progress, context, source_file)
                    VALUES (?, ?, ?, ?, ?)
                """, (item_id, pulse_date, had_progress, context, source_file))

                row_count += 1
            continue

        # Try table pattern
        table_match = table_pattern.match(line)
        if table_match:
            bold_span = table_match.group(1)

            # Same prefix-derived regex as the bullet branch.
            item_ids = ITEM_ID_RE.findall(bold_span)

            for item_id in item_ids:
                had_progress = _detect_progress(line, arrow_pattern)
                context = _extract_context(line[table_match.end():])

                conn.execute("""
                    INSERT INTO pulse_mentions (item_id, pulse_date, had_progress, context, source_file)
                    VALUES (?, ?, ?, ?, ?)
                """, (item_id, pulse_date, had_progress, context, source_file))

                row_count += 1
            continue

    return row_count


def _detect_progress(line: str, arrow_pattern) -> int:
    """Determine if a line indicates progress. Returns 0 or 1."""
    # Check for arrow pattern: progress_count or progress with digit before → and digit after
    m = arrow_pattern.search(line)
    if m and m.group(1) != m.group(2):
        return 1

    # Check for last_progress mention
    if "last_progress" in line:
        return 1

    # Check for NEW or (new)
    if "NEW" in line or "(new)" in line:
        return 1

    return 0


def _extract_context(text: str) -> str:
    """Extract and clean context text. Returns context truncated to 300 chars."""
    context = text.lstrip()
    if context.startswith("— ") or context.startswith("—"):
        context = context.lstrip("—").lstrip()
    return context[:300]


# ---------------------------------------------------------------------------
# FTS rebuild
# ---------------------------------------------------------------------------

def rebuild_fts(conn: sqlite3.Connection):
    conn.execute("DELETE FROM items_fts")
    conn.execute("""
        INSERT INTO items_fts (id, title, blocked_reason)
        SELECT id, title, COALESCE(blocked_reason, '')
        FROM items
    """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def sync():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run init-db.py first.")
        sys.exit(1)

    w_bi, w_ts, w_dr, flag_weeks, escalate_weeks, stale_mention_threshold = load_weights()
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    files = sorted(
        p for p in BACKLOG_DIR.glob("*.md")
        if not p.name.startswith("_completed")
    )

    if not files:
        print("No backlog files found.")
        conn.close()
        return

    synced = 0
    score_changes = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        fm_str, body = split_frontmatter(content)

        if fm_str is None:
            print(f"WARN [{path.name}]: no frontmatter, file skipped", file=sys.stderr)
            continue

        data = parse_frontmatter(fm_str, path.name)
        item_id = data.get("id")
        if not item_id:
            print(f"WARN [{path.name}]: no id field, file skipped", file=sys.stderr)
            continue

        priority_score, stale_weeks, escalation_level = compute_fields(
            data, w_bi, w_ts, w_dr,
            flag_weeks, escalate_weeks, stale_mention_threshold
        )

        # Detect score change for reporting
        old_score = data.get("priority_score")
        score_changed = (old_score is not None and
                         abs(float(old_score) - priority_score) > 0.01)
        if score_changed:
            score_changes.append(
                f"  {item_id}: score {float(old_score):.2f} → {priority_score:.2f}"
            )

        step = normalized_step_fields(item_id, data)
        validate_step_fields(item_id, step)

        # Upsert into DB
        upsert_item(conn, data, priority_score, stale_weeks, escalation_level, step)

        # Snapshot score history
        snapshot_score_history(conn, item_id, data, priority_score, stale_weeks, escalation_level)

        # Write computed fields back to frontmatter
        fm_updated = fm_str
        fm_updated = set_frontmatter_field(fm_updated, "priority_score", priority_score)
        fm_updated = set_frontmatter_field(fm_updated, "stale_weeks", stale_weeks)
        fm_updated = set_frontmatter_field(fm_updated, "escalation_level", escalation_level)

        if fm_updated != fm_str:
            path.write_text(rebuild_file(fm_updated, body), encoding="utf-8")

        status = data.get("status", "?")
        print(f"  {item_id:12s}  score={priority_score:5.1f}  stale={stale_weeks}w"
              f"  esc={escalation_level}  [{status}]")
        synced += 1

    # Commit item upserts and score snapshots before processing pulses
    conn.commit()

    # Populate pulse_mentions from pulse-checks files
    pulse_row_count, pulse_file_count = populate_pulse_mentions(conn)
    conn.commit()

    # Rebuild FTS index
    rebuild_fts(conn)
    conn.commit()
    conn.close()

    print(f"\nSynced {synced} items into {DB_PATH}")
    print(f"pulse_mentions: rebuilt {pulse_row_count} rows from {pulse_file_count} pulse files scanned")
    print(f"score_history: snapshotted {synced} items for {date.today().isoformat()}")
    if score_changes:
        print(f"\nScore changes ({len(score_changes)}):")
        for line in score_changes:
            print(line)
    else:
        print("No score changes.")


def rotate_run_history():
    # workflow-state.json is read at the start of every scan session — keep it
    # small by rotating old runs[] entries into run-archive.json (read by /retro).
    import subprocess
    script = Path(__file__).resolve().parent / "rotate-run-history.py"
    subprocess.run([sys.executable, str(script)], check=False)


if __name__ == "__main__":
    sync()
    if "--no-rotate" not in sys.argv:
        rotate_run_history()
