# Command: /status

Show the current state of the Six Eyes system at a glance. No external API calls — reads local files only.

## What to output

```
## Six Eyes — System Status
[timestamp]

### Last Runs
| Skill            | Last Run     | Age     |
|------------------|--------------|---------|
| pulse-scan       | [date]       | [N days ago] |
| staleness-check  | [date]       | [N days ago] |
| weekly-brief     | [date]       | [N days ago] |
| meeting-ingest   | [date]       | [N days ago] |
| opportunity-scan | [date]       | [N days ago] |

### Backlog Summary
One row per category present in the backlog (omit any with no items):
| Category    | Active | Blocked | Watching | Backburner |
|-------------|--------|---------|----------|------------|
| Onboarding  | N      | N       | N        | N          |
| Checkout    | N      | N       | N        | N          |
| Billing     | N      | N       | N        | N          |
| Lifecycle   | N      | N       | N        | N          |
| Platform    | N      | N       | N        | N          |

### Escalation Flags
Items at or above escalation threshold (stale_weeks ≥ 4 or escalation_level > 0):
- [item-id] [title] — [stale_weeks]w stale, level [N]

### Cross-Module Registry
[N] active cross-module links. Last updated: [date].

### Data Freshness
- Pulse checks: newest is [date] ([N days old])
- Meetings: [N] files in data/meetings/, newest is [date]
- SQLite last synced: [date from workflow-state.json]
```

## How to populate it

1. Read `data/state/workflow-state.json` for last-run timestamps per skill
2. Read all `data/backlog/*.md` frontmatter — count by module and status
3. Query `metadata/sixeyes.db` for items where `escalation_level > 0` or `stale_weeks >= 4`
   - If SQLite unavailable, derive from frontmatter `stale_weeks` field instead
4. Read `data/signals/cross-module-registry.json` for link count and `updated` date
5. List `data/pulse-checks/` subdirs for newest file date
6. List `data/meetings/` for count and newest file date

Keep the output compact — this is a quick diagnostic, not a report.
