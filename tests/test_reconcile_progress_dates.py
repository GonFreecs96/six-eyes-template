"""Heading recognition in scripts/reconcile-progress-dates.py (2026-10-09 fix:
'### YYYY-MM-DD' pulse-style headings were invisible to the reconciler)."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reconcile-progress-dates.py"


@pytest.fixture()
def rpd(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("reconcile_progress_dates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    return mod


def item(tmp_path, notes, lp="2026-07-01", lt="2026-07-01", status="active"):
    p = tmp_path / "X-001-test.md"
    p.write_text(
        f"---\nid: X-001\nstatus: {status}\nlast_progress: {lp}\nlast_touched: {lt}\n---\n"
        f"## Context\nx\n\n## Notes\n\n{notes}\n"
    )
    return p


def test_bold_iso_heading_auto_applies_both_dates(rpd, tmp_path):
    f = rpd.analyze(item(tmp_path, "**2026-08-10 — Found the root cause.** Details."))
    assert f["action"] == "apply"
    assert f["set_last_progress"] == "2026-08-10"
    assert f["set_last_touched"] == "2026-08-10"


def test_md_heading_is_recognised_but_only_touch_is_applied(rpd, tmp_path):
    f = rpd.analyze(item(tmp_path, "### 2026-08-10 — W33 Pulse\nONB-001 moved to QA."))
    assert f["action"] == "apply"
    assert f["set_last_touched"] == "2026-08-10"
    assert f["set_last_progress"] is None
    assert f["review_last_progress"] == "2026-08-10"


def test_md_heading_already_in_last_touched_is_not_reflagged(rpd, tmp_path):
    f = rpd.analyze(item(tmp_path, "### 2026-08-10 — W33 Pulse — no new signal",
                         lt="2026-08-10"))
    assert f["action"] == "none"


def test_bold_heading_newer_than_md_heading_still_auto_applies(rpd, tmp_path):
    notes = "### 2026-08-03 — W32 Pulse\nx\n\n**2026-08-10 — Shipped and verified.**"
    f = rpd.analyze(item(tmp_path, notes))
    assert f["action"] == "apply"
    assert f["set_last_progress"] == "2026-08-10"


def test_old_month_headings_on_current_item_are_not_flagged(rpd, tmp_path):
    notes = "**Jun 15 (created).** x\n\n**2026-09-01 — Reactivated.** y"
    f = rpd.analyze(item(tmp_path, notes, lp="2026-09-01", lt="2026-09-01"))
    assert f["action"] == "none"


def test_no_signal_entry_routes_to_review(rpd, tmp_path):
    f = rpd.analyze(item(tmp_path, "**2026-08-10 — Pulse: no signal this week.**"))
    assert f["action"] == "review"
