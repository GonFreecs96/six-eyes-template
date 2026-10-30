"""Scoring, staleness and pulse-parsing logic in scripts/sync-metadata.py.

Pinned fixtures, no repo state: `today` and the active-week set are passed in,
pulse files live in tmp_path, and the SQLite table is in-memory. The regression
cases at the bottom cover the bug where the pulse-mention regex carried the
private original's item prefixes and matched none of this template's IDs.
"""
import importlib.util
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))  # sync-metadata imports dashboard_helpers


@pytest.fixture(scope="module")
def sm():
    spec = importlib.util.spec_from_file_location("sync_metadata", SCRIPTS / "sync-metadata.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Shipped config/scoring-weights.json values, pinned so a config change is a
# deliberate test change too.
W_BI, W_TS, W_DR = 0.40, 0.35, 0.25
FLAG, ESCALATE, MENTION = 2, 6, 3
TODAY = date(2026, 10, 30)
CALENDAR = set()  # empty active-week set -> compute_fields falls back to calendar weeks


def fields(sm, active_weeks=CALENDAR, **item):
    data = {"business_impact": 3, "time_sensitivity": 3, "data_readiness": 3,
            "last_progress": TODAY.isoformat(), "status": "active",
            "mention_count": 0, "progress_count": 0}
    data.update(item)
    return sm.compute_fields(data, W_BI, W_TS, W_DR, FLAG, ESCALATE, MENTION,
                             today=TODAY, active_weeks=active_weeks)


def weeks_ago(n):
    return date.fromordinal(TODAY.toordinal() - 7 * n).isoformat()


# --- config is the single source --------------------------------------------

def test_load_weights_reads_shipped_config(sm):
    assert sm.load_weights() == (W_BI, W_TS, W_DR, FLAG, ESCALATE, MENTION)


def test_load_weights_has_no_silent_threshold_defaults(sm, tmp_path, monkeypatch):
    p = tmp_path / "w.json"
    p.write_text('{"weights": {"business_impact": 0.4, "time_sensitivity": 0.35, '
                 '"data_readiness": 0.25}, "staleness_thresholds": {"flag_weeks": 2}}')
    monkeypatch.setattr(sm, "WEIGHTS_PATH", p)
    with pytest.raises(KeyError):
        sm.load_weights()


# --- priority score -----------------------------------------------------------

@pytest.mark.parametrize("bi,ts,dr,expected", [
    (5, 5, 5, 100.0),
    (1, 1, 1, 20.0),
    (4, 4, 4, 80.0),
    (5, 3, 1, 66.0),   # (2.0 + 1.05 + 0.25) * 20
    (0, 0, 0, 0.0),
])
def test_priority_score_is_weighted_sum_times_20(sm, bi, ts, dr, expected):
    score, _, _ = fields(sm, business_impact=bi, time_sensitivity=ts, data_readiness=dr)
    assert score == expected


def test_missing_dimensions_count_as_zero(sm):
    score, _, _ = fields(sm, business_impact=None, time_sensitivity="", data_readiness=4)
    assert score == 20.0


# --- active-week counting -----------------------------------------------------

def test_active_weeks_counts_only_weeks_with_a_pulse(sm):
    active = {(2026, 41), (2026, 42)}
    assert sm.active_weeks_since(date(2026, 9, 1), TODAY, active) == 2


def test_idle_gap_does_not_age_the_backlog(sm):
    active = {(2026, 41), (2026, 42)}
    # Four months idle before the two active weeks still counts as 2.
    assert sm.active_weeks_since(date(2026, 6, 1), TODAY, active) == 2


def test_active_weeks_are_strictly_after_start(sm):
    active = {(2026, 44)}  # the week containing TODAY (Fri 2026-10-30)
    assert sm.active_weeks_since(TODAY, TODAY, active) == 0
    assert sm.active_weeks_since(date(2026, 10, 23), TODAY, active) == 1


def test_no_pulse_archive_falls_back_to_calendar_weeks(sm):
    assert sm.active_weeks_since(date(2026, 9, 1), TODAY, set()) == 8   # 59 days // 7


def test_system_active_weeks_reads_pulse_filenames(sm, tmp_path, monkeypatch):
    (tmp_path / "data" / "pulse-checks").mkdir(parents=True)
    (tmp_path / "data" / "pulse-checks" / "2026-W41-pulse.md").write_text("")
    (tmp_path / "data" / "pulse-checks" / "2026-W42-pulse.md").write_text("")
    (tmp_path / "data" / "pulse-checks" / "README.md").write_text("")
    monkeypatch.setattr(sm, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sm, "ACTIVE_WEEKS_CACHE", None)
    assert sm.system_active_weeks() == {(2026, 41), (2026, 42)}


# --- escalation ladder --------------------------------------------------------

@pytest.mark.parametrize("stale,level", [(0, 0), (1, 0), (2, 1), (5, 1), (6, 2), (12, 2)])
def test_time_ladder_uses_flag_and_escalate_weeks(sm, stale, level):
    _, stale_weeks, esc = fields(sm, last_progress=weeks_ago(stale))
    assert (stale_weeks, esc) == (stale, level)


@pytest.mark.parametrize("raw", [None, "", "not-a-date", "2026-13-40"])
def test_missing_or_bad_last_progress_is_treated_as_fresh(sm, raw):
    _, stale_weeks, esc = fields(sm, last_progress=raw)
    assert (stale_weeks, esc) == (0, 0)


# --- mention-gap override -----------------------------------------------------

def test_mention_gap_escalates_a_flagged_high_score_item_to_level_2(sm):
    score, _, esc = fields(sm, business_impact=4, time_sensitivity=4, data_readiness=4,
                           last_progress=weeks_ago(2), mention_count=5, progress_count=2)
    assert score > 60 and esc == 2


def test_mention_gap_only_flags_a_low_score_item(sm):
    score, _, esc = fields(sm, business_impact=3, time_sensitivity=3, data_readiness=3,
                           last_progress=weeks_ago(2), mention_count=5, progress_count=2)
    assert score == 60.0 and esc == 1   # score must be strictly > 60 for level 2


def test_mention_gap_is_ignored_while_item_is_fresh(sm):
    # Lifetime gap, but it progressed this week: stays at level 0.
    _, _, esc = fields(sm, business_impact=5, time_sensitivity=5, data_readiness=5,
                       last_progress=TODAY.isoformat(), mention_count=9, progress_count=1)
    assert esc == 0


def test_mention_gap_below_threshold_does_nothing(sm):
    _, _, esc = fields(sm, business_impact=5, time_sensitivity=5, data_readiness=5,
                       last_progress=weeks_ago(2), mention_count=4, progress_count=2)
    assert esc == 1


def test_mention_gap_never_lowers_the_time_ladder(sm):
    _, _, esc = fields(sm, business_impact=1, time_sensitivity=1, data_readiness=1,
                       last_progress=weeks_ago(6), mention_count=9, progress_count=0)
    assert esc == 2


# --- terminal-status forcing --------------------------------------------------

@pytest.mark.parametrize("status", ["done", "backburner", "Done", " BACKBURNER "])
def test_terminal_status_forces_level_0(sm, status):
    _, stale_weeks, esc = fields(sm, status=status, last_progress=weeks_ago(10),
                                 business_impact=5, time_sensitivity=5, data_readiness=5,
                                 mention_count=9, progress_count=0)
    assert stale_weeks == 10 and esc == 0


@pytest.mark.parametrize("status", ["active", "blocked", "waiting", "monitoring", None])
def test_non_terminal_statuses_keep_escalating(sm, status):
    _, _, esc = fields(sm, status=status, last_progress=weeks_ago(10))
    assert esc == 2


# --- pulse parsing ------------------------------------------------------------

PULSE_W41 = """# Pulse Check — W41

## Shipped

- **ACMECHK-138** — Rename pay-flow steps (Done). Keeps [[CHK-003]] hot.

## Backlog Updates

- **[[ONB-001]]** — mention 4→5; progress 2→3 after W41 deep dive.
- **[[CHK-003]]** — mention 3→4; progress 1→2; escalation 0→1 (2w stale).
- **[[PLT-009]]** — mention 2→3; no progress change.
- **ACMEONB-1103** — a Jira key in the wrong section; must not mint ONB-1103.
- **[[BIL-005]], [[BIL-006]]** — joint note; last_progress 2026-10-03.

## Backlog Updates (staged)

| Item | Change |
| **[[LIF-007]]** | NEW — created this week |
| **[[LIF-008]]** | mention 1→2; progress 1→1 |

## Notes

- **[[ONB-010]]** — outside any Backlog Updates section, must be ignored.
"""


@pytest.fixture()
def pulse_db(sm, tmp_path, monkeypatch):
    pulse_dir = tmp_path / "data" / "pulse-checks"
    pulse_dir.mkdir(parents=True)
    (pulse_dir / "2026-W41-pulse.md").write_text(PULSE_W41)
    (pulse_dir / "notes.md").write_text(PULSE_W41)  # not YYYY-Www: skipped
    monkeypatch.setattr(sm, "REPO_ROOT", tmp_path)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE pulse_mentions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "item_id TEXT, pulse_date TEXT, had_progress INTEGER, context TEXT, source_file TEXT)")
    return conn


def rows(conn):
    return {r[0]: r for r in conn.execute(
        "SELECT item_id, pulse_date, had_progress, context, source_file FROM pulse_mentions")}


def test_pulse_sections_bullets_and_tables_are_parsed(sm, pulse_db):
    n_rows, n_files = sm.populate_pulse_mentions(pulse_db)
    got = rows(pulse_db)
    assert (n_rows, n_files) == (7, 1)
    assert set(got) == {"ONB-001", "CHK-003", "PLT-009", "BIL-005", "BIL-006", "LIF-007", "LIF-008"}
    assert got["ONB-001"][1] == "2026-10-05"            # Monday of ISO week 41
    assert got["ONB-001"][4] == "2026-W41-pulse.md"
    assert got["ONB-001"][3].startswith("mention 4→5")  # leading em-dash stripped


def test_progress_detection_per_row(sm, pulse_db):
    sm.populate_pulse_mentions(pulse_db)
    got = rows(pulse_db)
    assert got["ONB-001"][2] == 1   # progress 2→3
    assert got["CHK-003"][2] == 1   # progress 1→2
    assert got["PLT-009"][2] == 0   # no progress change
    assert got["BIL-005"][2] == 1   # last_progress mentioned
    assert got["LIF-007"][2] == 1   # NEW
    assert got["LIF-008"][2] == 0   # progress 1→1


def test_jira_keys_and_other_sections_do_not_mint_rows(sm, pulse_db):
    sm.populate_pulse_mentions(pulse_db)
    got = rows(pulse_db)
    assert "ONB-1103" not in got     # left-boundary guard on ACMEONB-1103
    assert "ONB-010" not in got      # mention outside a Backlog Updates section
    assert "CHK-138" not in got


def test_populate_is_a_full_rebuild(sm, pulse_db):
    pulse_db.execute("INSERT INTO pulse_mentions (item_id) VALUES ('STALE-1')")
    sm.populate_pulse_mentions(pulse_db)
    assert "STALE-1" not in rows(pulse_db)


@pytest.mark.parametrize("line,expected", [
    ("mention 4→5; progress 2→3", 1),
    ("progress_count 2 -> 3", 1),
    ("progress 3→3", 0),
    ("last_progress 2026-10-12", 1),
    ("NEW item", 1),
    ("(new) item", 1),
    ("mention 2→3; no progress change", 0),
])
def test_detect_progress(sm, line, expected):
    pattern = re.compile(r"progress(?:_count)?[`\s]*(\d+)\s*(?:→|->)\s*(\d+)")
    assert sm._detect_progress(line, pattern) == expected


# --- regression: item-ID prefixes come from config/modules.json ---------------

def test_item_id_regex_matches_every_shipped_backlog_id(sm):
    """The old hard-coded regex matched none of this template's prefixes, so
    pulse_mentions was always empty. The configured regex must match every ID
    actually used in data/backlog/."""
    ids = []
    for p in (ROOT / "data" / "backlog").glob("*.md"):
        m = re.search(r"^id:\s*(\S+)", p.read_text(), re.MULTILINE)
        if m:
            ids.append(m.group(1))
    assert ids, "no backlog fixtures found"
    for item_id in ids:
        assert sm.ITEM_ID_RE.findall(f"**[[{item_id}]]**") == [item_id], item_id


def test_item_id_regex_is_built_from_module_config(sm):
    import dashboard_helpers as dh
    import json
    cfg = json.loads((ROOT / "config" / "modules.json").read_text())
    prefixes = [c["id_prefix"] for c in cfg["categories"]]
    assert dh.load_item_id_prefixes() == prefixes
    assert sorted(prefixes) == ["BIL", "CHK", "LIF", "ONB", "PLT"]


def test_item_id_regex_ignores_jira_keys_and_empty_config(sm):
    import dashboard_helpers as dh
    rx = dh.item_id_regex(["ONB", "CHK"])
    assert rx.findall("[[ONB-001]] ACMEONB-201 CHK-3 xCHK-4 BIL-005") == ["ONB-001", "CHK-3"]
    assert dh.item_id_regex([]).findall("ONB-001") == []


def test_shipped_pulses_populate_mentions(sm, monkeypatch):
    """End-to-end on the committed fixtures: both shipped pulse files yield rows."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE pulse_mentions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "item_id TEXT, pulse_date TEXT, had_progress INTEGER, context TEXT, source_file TEXT)")
    monkeypatch.setattr(sm, "REPO_ROOT", ROOT)
    n_rows, n_files = sm.populate_pulse_mentions(conn)
    assert n_files == 2 and n_rows >= 10
    assert {"ONB-001", "CHK-003", "BIL-005", "LIF-007", "PLT-009"} <= set(rows(conn))
