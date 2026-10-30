#!/usr/bin/env python3
"""Slim governed-repo knowledge promotion (local plan + ledger; optional apply).

Reads data/bq-knowledge.md, runs a lightweight privacy pass, appends a ledger
entry under data/release-ledger/, and writes a promotion plan under
outputs/governed-promotion/. When config/runtime.yaml governed_repo or
GOVERNED_REPO is set, the plan describes patch targets in that repo; otherwise
the plan is local-only with setup instructions.

Full GitHub Actions draft-PR automation is documented as a roadmap item.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BQ_KNOWLEDGE = REPO_ROOT / "data" / "bq-knowledge.md"
LEDGER = REPO_ROOT / "data" / "release-ledger" / "events.yaml"
OUT_DIR = REPO_ROOT / "outputs" / "governed-promotion"
RUNTIME = REPO_ROOT / "config" / "runtime.yaml"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+")


def load_governed_repo() -> Path | None:
    env = os.environ.get("GOVERNED_REPO")
    if env:
        p = Path(env).expanduser()
        return p if p.is_dir() else None
    if RUNTIME.is_file():
        cfg = yaml.safe_load(RUNTIME.read_text()) or {}
        gr = cfg.get("governed_repo")
        if gr:
            p = Path(gr).expanduser()
            return p if p.is_dir() else None
    return None


def privacy_pass(text: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    if EMAIL_RE.search(text):
        findings.append("email-like pattern")
        text = EMAIL_RE.sub("[redacted-email]", text)
    if SECRET_RE.search(text):
        findings.append("secret-like pattern")
        text = SECRET_RE.sub("[redacted-secret]", text)
    return text, findings


def load_bq_knowledge() -> str:
    if not BQ_KNOWLEDGE.is_file():
        return ""
    return BQ_KNOWLEDGE.read_text()


def append_ledger(event: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if LEDGER.is_file():
        existing = yaml.safe_load(LEDGER.read_text()) or []
    existing.append(event)
    LEDGER.write_text(yaml.safe_dump(existing, sort_keys=False))


def build_plan(clean_text: str, governed: Path | None, privacy_findings: list[str]) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sections = [s.strip() for s in re.split(r"^##\s+", clean_text, flags=re.M) if s.strip()]
    candidates = []
    for block in sections[:5]:
        title = block.split("\n", 1)[0].strip()
        candidates.append({"section": title, "action": "review_for_governed_metric_or_guardrail"})
    plan = {
        "generated_at": ts,
        "source": str(BQ_KNOWLEDGE.relative_to(REPO_ROOT)),
        "governed_repo": str(governed) if governed else None,
        "privacy_findings": privacy_findings,
        "candidate_sections": candidates,
        "patches": [],
    }
    if governed:
        plan["patches"].append(
            {
                "target_repo": str(governed),
                "path": "docs/warehouse-notes/from-six-eyes.md",
                "summary": "Append sanitized excerpt from bq-knowledge (human review required)",
            }
        )
    else:
        plan["note"] = (
            "Set governed_repo in config/runtime.yaml or export GOVERNED_REPO=/path/to/repo "
            "to attach real patch targets. This run still wrote the plan and ledger entry locally."
        )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed knowledge promotion (local plan)")
    parser.add_argument("--json", action="store_true", help="Print plan JSON to stdout")
    args = parser.parse_args()

    raw = load_bq_knowledge()
    clean, privacy_findings = privacy_pass(raw)
    governed = load_governed_repo()
    plan = build_plan(clean, governed, privacy_findings)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plan_path = OUT_DIR / "promotion-plan.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")

    append_ledger(
        {
            "at": plan["generated_at"],
            "kind": "governed_knowledge_plan",
            "plan_path": str(plan_path.relative_to(REPO_ROOT)),
            "governed_repo": plan["governed_repo"],
            "privacy_findings": privacy_findings,
        }
    )

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"Wrote {plan_path.relative_to(REPO_ROOT)}")
        if not governed:
            print(plan["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
