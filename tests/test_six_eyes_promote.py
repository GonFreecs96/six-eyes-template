"""Conflict-aware promote in scripts/six-eyes-promote.py (2026-10-13: a blind `cp`
promote silently reverted 20 lines a concurrent session committed to
data/bq-knowledge.md mid-run)."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "six-eyes-promote.py"
BACKLOG = "data/backlog/ONB-001-x.md"
FM = "---\nid: ONB-001\nlast_touched: 2026-10-01\npriority_score: 50.0\nstale_weeks: 1\n---\n"


def sh(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def commit(repo, msg="c"):
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", msg)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    sh(repo, "init", "-q")
    sh(repo, "config", "user.email", "t@t")
    sh(repo, "config", "user.name", "t")
    write(repo, ".gitignore", "data/staging/\n")
    write(repo, "data/bq-knowledge.md", "## A\nalpha\n\n## B\nbeta\n")
    write(repo, BACKLOG, FM + "## Notes\n\n**2026-10-01 — first.**\n")
    write(repo, "outputs/priority-dashboard.md", "dash v1\n")
    write(repo, "outputs/untouched.md", "u v1\n")
    commit(repo, "init")
    spec = importlib.util.spec_from_file_location("six_eyes_promote", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    return mod, repo


def stage(repo, rel, text):
    write(repo, f"data/staging/staged/{rel}", text)


def by_path(rows):
    return {r["path"]: r for r in rows}


def test_concurrent_commit_to_bq_knowledge_is_merged_not_reverted(env):
    mod, repo = env
    mod.record_base()
    # Staged step appends a section at the end...
    stage(repo, "data/bq-knowledge.md", "## A\nalpha\n\n## B\nbeta\n\n## C\nstaged gamma\n")
    # ...while another session commits an addition under ## A.
    write(repo, "data/bq-knowledge.md", "## A\nalpha\nconcurrent line\n\n## B\nbeta\n")
    commit(repo, "concurrent")
    rows = by_path(mod.check(mod.load_base()))
    assert rows["data/bq-knowledge.md"]["action"] == "CONFLICT-merge"
    assert "(committed)" in rows["data/bq-knowledge.md"]["reason"]
    res = by_path(mod.promote(mod.load_base(), None, False))
    assert not res["data/bq-knowledge.md"]["needs_mark"]
    text = (repo / "data/bq-knowledge.md").read_text()
    assert "concurrent line" in text and "staged gamma" in text


def test_unconflicted_files_promote_and_creates_work(env):
    mod, repo = env
    mod.record_base()
    stage(repo, "outputs/untouched.md", "u v2\n")
    stage(repo, "data/pulse-checks/2026-W42-pulse.md", "pulse\n")
    rows = by_path(mod.promote(mod.load_base(), None, False))
    assert rows["outputs/untouched.md"]["action"] == "overwrite"
    assert rows["data/pulse-checks/2026-W42-pulse.md"]["action"] == "create"
    assert (repo / "outputs/untouched.md").read_text() == "u v2\n"
    assert (repo / "data/pulse-checks/2026-W42-pulse.md").read_text() == "pulse\n"


def test_uncommitted_edit_to_non_mergeable_file_is_skipped(env):
    mod, repo = env
    mod.record_base()
    stage(repo, "outputs/priority-dashboard.md", "dash staged\n")
    write(repo, "outputs/priority-dashboard.md", "dash hand-edited\n")
    rows = by_path(mod.promote(mod.load_base(), None, False))
    r = rows["outputs/priority-dashboard.md"]
    assert r["action"] == "CONFLICT-skip" and r["needs_mark"]
    assert "uncommitted" in r["reason"]
    assert (repo / "outputs/priority-dashboard.md").read_text() == "dash hand-edited\n"


def test_dirty_at_start_is_base_not_drift(env):
    mod, repo = env
    write(repo, "outputs/priority-dashboard.md", "dirty before run\n")
    mod.record_base()
    stage(repo, "outputs/priority-dashboard.md", "dash staged\n")
    assert by_path(mod.check(mod.load_base()))["outputs/priority-dashboard.md"]["conflict"] is False


def test_computed_field_only_conflict_resolves_to_live(env):
    mod, repo = env
    mod.record_base()
    stage(repo, BACKLOG, FM.replace("priority_score: 50.0", "priority_score: 61.0")
          + "## Notes\n\n**2026-10-01 — first.**\n\n**2026-10-13 — staged note.**\n")
    write(repo, BACKLOG, FM.replace("priority_score: 50.0", "priority_score: 55.0")
          + "## Notes\n\n**2026-10-01 — first.**\n")
    res = by_path(mod.promote(mod.load_base(), None, False))
    assert not res[BACKLOG]["needs_mark"]
    text = (repo / BACKLOG).read_text()
    assert "priority_score: 55.0" in text and "staged note" in text and "<<<<<<<" not in text


def test_real_notes_conflict_leaves_live_untouched(env):
    mod, repo = env
    mod.record_base()
    stage(repo, BACKLOG, FM + "## Notes\n\n**2026-10-01 — first.**\n\n**2026-10-13 — staged.**\n")
    live = FM + "## Notes\n\n**2026-10-01 — first.**\n\n**2026-10-13 — concurrent.**\n"
    write(repo, BACKLOG, live)
    res = by_path(mod.promote(mod.load_base(), None, False))
    assert res[BACKLOG]["needs_mark"]
    assert (repo / BACKLOG).read_text() == live
    marked = (repo / "data/staging/conflicts" / BACKLOG).read_text()
    assert "<<<<<<< live" in marked and "staged." in marked


def test_created_by_someone_else_is_skipped(env):
    mod, repo = env
    mod.record_base()
    stage(repo, "data/pulse-checks/2026-W42-pulse.md", "staged pulse\n")
    write(repo, "data/pulse-checks/2026-W42-pulse.md", "other session pulse\n")
    r = by_path(mod.check(mod.load_base()))["data/pulse-checks/2026-W42-pulse.md"]
    assert r["action"] == "CONFLICT-skip"


def test_missing_base_refuses_promote(env):
    mod, repo = env
    stage(repo, "outputs/untouched.md", "u v2\n")
    with pytest.raises(SystemExit):
        mod.promote(None, None, False)
    assert (repo / "outputs/untouched.md").read_text() == "u v1\n"


def test_only_subset(env):
    mod, repo = env
    mod.record_base()
    stage(repo, "outputs/untouched.md", "u v2\n")
    stage(repo, "outputs/priority-dashboard.md", "dash v2\n")
    rows = mod.promote(mod.load_base(), ["outputs/untouched.md"], False)
    assert [r["path"] for r in rows] == ["outputs/untouched.md"]
    assert (repo / "outputs/priority-dashboard.md").read_text() == "dash v1\n"
