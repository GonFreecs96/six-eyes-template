#!/usr/bin/env python3
"""Rotate workflow-state.json's runs[] into data/state/run-archive.json.

workflow-state.json is read at the start of every scan session, so it must stay
small. Full run history is only needed by /retro, which reads the archive.
Keeps the KEEP most-recent entries (by timestamp) in workflow-state.json and
moves the rest to the archive, chronologically sorted, deduped on full entry
content (several distinct runs can share a timestamp, e.g. batched close-loops).
Idempotent — safe to run after every run-record append.
"""
import json
from pathlib import Path

KEEP = 3
STATE = Path(__file__).resolve().parent.parent / "data/state/workflow-state.json"
ARCHIVE = STATE.parent / "run-archive.json"


def main():
    state = json.loads(STATE.read_text())
    runs = state.get("runs", [])
    if len(runs) <= KEEP:
        print(f"runs[] has {len(runs)} entries (<= {KEEP}); nothing to rotate")
        return

    archive = json.loads(ARCHIVE.read_text()) if ARCHIVE.exists() else []
    runs.sort(key=lambda r: r.get("timestamp", ""))
    to_archive = runs[:-KEEP]

    seen = {json.dumps(r, sort_keys=True) for r in archive}
    added = 0
    for r in to_archive:
        key = json.dumps(r, sort_keys=True)
        if key not in seen:
            archive.append(r)
            seen.add(key)
            added += 1
    archive.sort(key=lambda r: r.get("timestamp", ""))

    state["runs"] = runs[-KEEP:]
    ARCHIVE.write_text(json.dumps(archive, indent=2) + "\n")
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    print(
        f"kept {KEEP} runs in workflow-state.json; archived {added} new "
        f"({len(archive)} total in {ARCHIVE.name})"
    )


if __name__ == "__main__":
    main()
