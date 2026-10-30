# Six Eyes run manifest — 2026-10-13

| Step | Skill | Staged outputs |
|---|---|---|
| 1 | pulse-scan | `staged/data/pulse-checks/2026-W42-pulse.md` |
| 2 | opportunity-scan | `staged/data/signals/cross-module-registry.json` (refresh) |
| 3 | staleness-check | metadata-only (no file staged) |
| 4 | weekly-brief | `staged/data/state/last-run-summary.md` |

**Gate:** Review staged diffs, then `python3 scripts/six-eyes-promote.py`.
