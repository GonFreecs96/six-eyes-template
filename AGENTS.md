# Agent entrypoint (Cursor / compat)

Same harness as `CLAUDE.md`. Load skills from `.claude/skills/`; follow outbound guardrails in `.claude/settings.json`.

## Quick routing

| Intent | Skill / script |
|--------|----------------|
| Weekly staged run | `six-eyes-run` → `scripts/six-eyes-run.sh` |
| Promote staging | `scripts/six-eyes-promote.py` |
| Jira pulse (offline/live) | `pulse-scan` |
| Meeting signals | `meeting-ingest` |
| BQ investigation | `agent-work`, `bq-investigator` agent |
| Voice pass | `voice-rewrite` + `SOUL.md` |
| Backlog UI | `backlog-board` / `webapp/backlog_board/` |

## Cursor

- Rule: `.cursor/rules/six-eyes-template.mdc`
- MCP template: `.cursor/mcp.json` (fill in your server URLs; no secrets in git)

## Tests

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```
