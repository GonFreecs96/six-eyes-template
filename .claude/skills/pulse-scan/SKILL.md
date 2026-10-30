---
name: pulse-scan
description: Weekly Jira scan → pulse check markdown + backlog touch-ups.
---

# pulse-scan

## Mode

Read `config/runtime.yaml` → `mode`:

- **offline** — load `sample-inputs/jira/{ACMEONB|ACMECHK|ACMEBIL|ACMELIF|ACMEPLT}.json` (or all `*.json` in that folder)
- **live** — MCP Jira search per `config/modules.json` project keys

## Output (staging-aware)

When `SIXEYES_STAGING=1`, write:

- `data/staging/staged/data/pulse-checks/YYYY-Www-pulse.md`
- Backlog updates under `data/staging/staged/data/backlog/`

Sections: Summary, Shipped, In Flight, Watch Items, Backlog Updates.

## Acme modules

ONB onboarding, CHK checkout, BIL billing, LIF lifecycle/retention, PLT platform analytics.

Pull Slack only ad hoc in other skills; pulse-scan is Jira-first.
