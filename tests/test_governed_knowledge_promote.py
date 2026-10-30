import importlib.util
import json
import sys
from pathlib import Path


def load_promote_module(repo_root: Path):
    script = repo_root / "scripts" / "governed_knowledge_promote.py"
    spec = importlib.util.spec_from_file_location("gkp", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_promotion_plan_without_governed_repo(tmp_path, monkeypatch):
    repo = tmp_path / "six-eyes"
    repo.mkdir()
    (repo / "config").mkdir()
    (repo / "data").mkdir()
    (repo / "scripts").mkdir()
    (repo / "outputs").mkdir()

    # Minimal tree for the script
    import shutil

    src = Path(__file__).resolve().parents[1]
    shutil.copy(src / "scripts" / "governed_knowledge_promote.py", repo / "scripts" / "governed_knowledge_promote.py")
    (repo / "config" / "runtime.yaml").write_text("mode: offline\ngoverned_repo: null\n")
    (repo / "data" / "bq-knowledge.md").write_text("## Signups\nTrial conversion baseline.\n")

    mod = load_promote_module(repo)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    monkeypatch.setattr(mod, "BQ_KNOWLEDGE", repo / "data" / "bq-knowledge.md")
    monkeypatch.setattr(mod, "LEDGER", repo / "data" / "release-ledger" / "events.yaml")
    monkeypatch.setattr(mod, "OUT_DIR", repo / "outputs" / "governed-promotion")
    monkeypatch.setattr(mod, "RUNTIME", repo / "config" / "runtime.yaml")
    monkeypatch.setattr(sys, "argv", ["governed_knowledge_promote.py"])

    assert mod.main() == 0
    plan = json.loads((repo / "outputs" / "governed-promotion" / "promotion-plan.json").read_text())
    assert plan["governed_repo"] is None
    assert "note" in plan


def test_promotion_plan_with_throwaway_governed_repo(tmp_path, monkeypatch):
    repo = tmp_path / "six-eyes"
    governed = tmp_path / "governed"
    governed.mkdir()
    (governed / "docs" / "warehouse-notes").mkdir(parents=True)

    repo.mkdir()
    for d in ("config", "data", "scripts", "outputs"):
        (repo / d).mkdir()
    import shutil

    src = Path(__file__).resolve().parents[1]
    shutil.copy(src / "scripts" / "governed_knowledge_promote.py", repo / "scripts" / "governed_knowledge_promote.py")
    (repo / "config" / "runtime.yaml").write_text(f"mode: offline\ngoverned_repo: {governed}\n")
    (repo / "data" / "bq-knowledge.md").write_text("## Events\nPartner referral id mapping.\n")

    mod = load_promote_module(repo)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    monkeypatch.setattr(mod, "BQ_KNOWLEDGE", repo / "data" / "bq-knowledge.md")
    monkeypatch.setattr(mod, "LEDGER", repo / "data" / "release-ledger" / "events.yaml")
    monkeypatch.setattr(mod, "OUT_DIR", repo / "outputs" / "governed-promotion")
    monkeypatch.setattr(mod, "RUNTIME", repo / "config" / "runtime.yaml")
    monkeypatch.setattr(sys, "argv", ["governed_knowledge_promote.py"])

    assert mod.main() == 0
    plan = json.loads((repo / "outputs" / "governed-promotion" / "promotion-plan.json").read_text())
    assert plan["governed_repo"] == str(governed)
    assert plan["patches"]
