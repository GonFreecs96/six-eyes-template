---
name: today
description: >
  Quick daily briefing: what needs my attention right now? Reads the priority
  dashboard, weekly briefing, and backlog state to surface the most urgent items
  with specific action recommendations and contact names.
allowed-tools: Read, Bash(python:*)
---

## Procedure

1. Read `outputs/priority-dashboard.md` for scored and ranked items.
2. Read `outputs/weekly-briefing.md` for the latest synthesis.
3. Read `data/state/last-run-summary.md` for the scan narrative.
4. List `data/backlog/` and read any active item files with `escalation_level >= 1` or `time_sensitivity >= 4`.
5. If any escalated item is warehouse-flavoured (title contains "BQ", "schema", `acme_analytics`, or the next action references SQL), skim tagged sections in `data/bq-knowledge.md` so recommendations don't repeat resolved investigations.

## Output

Respond conversationally — no file creation. Keep it to ~15 lines max.

**1. Top 3 actions for today**
Pull from the weekly briefing's "What needs my attention" section and the priority dashboard's escalation candidates. For each:
- What to do (specific: "run X query", "ping Y on Slack", "review Z PR")
- Why now (what triggered it)
- Who to contact (by name, from the dashboard or backlog item)

**2. Stale items check**
If any items are at escalation_level 2, call them out explicitly: "[Item] has been stuck for N weeks — decision needed: escalate, descope, or close."

**3. What's coming**
One or two sentences on what's likely to need attention later this week based on in-flight items approaching QA or prod.

## Tone

Direct, no preamble. If nothing is urgent, say "Nothing critical today" and mention when the next pulse-scan is due. Don't manufacture urgency.
