---
name: weekly-brief
description: >
  Synthesizes all signal sources into a single weekly briefing answering:
  what shipped, what's at risk, what's stale, what needs attention, and
  who should I talk to. Run after pulse-scan and staleness-check.
allowed-tools: Read, Write, Bash(python:*)
---

## Prerequisites

Read only these compressed inputs — do NOT re-read raw Jira or Slack data:

1. `data/state/last-run-summary.md` — narrative from staleness-check
2. `outputs/priority-dashboard.md` — scored and ranked items
3. Most recent pulse check from `data/pulse-checks/`
4. `data/signals/cross-module-registry.json` — cross-module correlations (may be empty until Phase 3)

## Output

Write `outputs/weekly-briefing.md` in this format:
```markdown
# Weekly Briefing — Week of [DATE]

## What shipped this week
Brief list of tickets that moved to Done/Closed with analytics implications.
Pull from the pulse check's "Shipped" section — summarize, don't repeat verbatim.

## What's at risk
Items where an analytics window is closing, a feature shipped without BQ verification,
or a schema change is in flight. Pull from the pulse check's "In Flight" section
and the priority dashboard's escalation candidates. Lead with the most time-sensitive.

## What's stale
Items from the priority dashboard's "Blocked Longest" and "Most Discussed Without
Progress" sections. For each: state the item, how long it's been stuck, and the
specific recommended action from the staleness-check output.

## What needs my attention this week
Top 3-5 concrete actions ordered by composite priority. For each:
1. **What:** One-line description
2. **Why now:** What triggered the urgency
3. **Next step:** Specific action (run a query, ping someone, review a PR)
4. **Who:** Name of the person to contact, if applicable

## Cross-module signals
Any items flagged in the cross-module registry or pulse check that span two or more categories.
If none, omit this section.
```

## Rules

- **Max length: ~800 words.** This is a briefing, not a report. If the analyst wants detail, they read the pulse check or backlog item files directly.
- **No filler.** If a section has nothing, omit it entirely rather than writing "nothing to report."
- **Name names.** "Ping Marco Chen about checkout step events" not "follow up with the engineering team."
- **Include the date context.** "ACMECHK-138 shipped October 8 — warehouse audit on promo-step gap not yet done" is more useful than "shipped recently."

## Approval

**Do NOT write the file until the operator approves.** Present the draft, wait for confirmation, then write to `outputs/weekly-briefing.md`.

## Staging mode (orchestrated runs)

When the invocation says **STAGING MODE** (or env `SIXEYES_STAGING=1`), this skill is
running inside `/six-eyes-run`. Do **not** present the approval gate. Instead:

1. Write the weekly briefing to `data/staging/staged/outputs/weekly-briefing.md`.
   In staging mode, read your compressed inputs from the **staged** copies if they
   exist (`data/staging/staged/outputs/priority-dashboard.md`,
   `data/staging/staged/data/state/last-run-summary.md`,
   `data/staging/staged/data/pulse-checks/…`) so the brief reflects this run's proposals,
   falling back to the live files when no staged copy exists.
2. Append a `## weekly-brief` section to `data/staging/run-manifest.md` with the brief's
   "what needs my attention" headline actions.