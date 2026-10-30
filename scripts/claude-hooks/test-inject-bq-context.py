#!/usr/bin/env python3
"""Tests for inject-bq-context.py using the repo config corpus."""
import json
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "inject-bq-context.py"
REPO = Path(__file__).resolve().parents[2]

FIXTURES = [
    {
        "name": "trial dedupe positive",
        "prompt": "count trial_started events by user_id in acme_analytics.events",
        "expect_ids": ["trial_started_double_fire"],
        "should_output": True,
    },
    {
        "name": "signup join positive",
        "prompt": "join signups to subscriptions on user_id",
        "expect_ids": ["signup_user_id_anchor"],
        "should_output": True,
    },
    {
        "name": "git status negative",
        "prompt": "what is git status",
        "should_output": False,
    },
]


def run_hook(prompt: str) -> dict | None:
    payload = json.dumps({"prompt": prompt})
    proc = subprocess.run(
        ["python3", str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        cwd=REPO,
        env={"CLAUDE_PROJECT_DIR": str(REPO), **dict(**__import__("os").environ)},
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    if not out:
        return None
    return json.loads(out)


def test_inject_fixtures():
    for fx in FIXTURES:
        result = run_hook(fx["prompt"])
        if not fx["should_output"]:
            assert result is None or not result.get("hookSpecificOutput"), fx["name"]
            continue
        assert result is not None, fx["name"]
        injected = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        for rid in fx.get("expect_ids", []):
            assert rid in injected, f"{fx['name']}: missing {rid}"


if __name__ == "__main__":
    test_inject_fixtures()
    print("OK")
