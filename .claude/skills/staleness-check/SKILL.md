---
name: staleness-check
description: >
  Computes priority scores, detects stale backlog items, identifies escalation
  candidates, and generates the priority dashboard. Run after pulse-scan or on demand.
allowed-tools: Read, Write, Bash(python:*)
---

## Prerequisites

1. Run the sync script to ensure SQLite is current:
```
   python scripts/sync-metadata.py
```
2. Read `config/scoring-weights.json` for thresholds.
3. Read `config/modules.json` → `categories` for contact (`pm`) lookup by module.

## Step 1 — Query priority roll-ups

Run the following SQLite queries against `metadata/sixeyes.db`:

**Waiting longest:**
```sql
SELECT id, title, module, stale_weeks, blocked_reason, priority_score
FROM items
WHERE status = 'waiting'
ORDER BY stale_weeks DESC, priority_score DESC
```

**Most discussed without progress:**
```sql
SELECT id, title, module, mention_count, progress_count,
       (mention_count - progress_count) AS stale_mentions, priority_score
FROM items
WHERE status NOT IN ('backburner', 'done')
  AND mention_count > progress_count
ORDER BY stale_mentions DESC, priority_score DESC
```

**Highest priority unactioned:**
```sql
SELECT id, title, module, priority_score, stale_weeks, status
FROM items
WHERE priority_score > 60
  AND stale_weeks > 1
  AND status NOT IN ('backburner', 'done')
ORDER BY priority_score DESC
```

**Escalation candidates:**
```sql
SELECT id, title, module, priority_score, escalation_level, stale_weeks, status
FROM items
WHERE escalation_level >= 1
  AND status NOT IN ('backburner', 'done')
ORDER BY priority_score * (1 + escalation_level * 0.5) DESC
```

**Cross-module items:**
```sql
SELECT id, title, module, cross_modules, priority_score, status
FROM items
WHERE cross_modules != '[]'
  AND status NOT IN ('backburner', 'done')
ORDER BY priority_score DESC
```

## Step 2 — Generate escalation recommendations

For each item returned by the **Escalation candidates** query above (`escalation_level >= 1`
AND status not in `backburner`/`done`), generate a specific
recommendation. Backburner/done items are terminal — they should never
surface as escalation candidates even if their `escalation_level` field wasn't reset at
close time; if you find one, that's a frontmatter cleanup opportunity (reset
`escalation_level` to 0), not an escalation to act on:

Thresholds come from `config/scoring-weights.json` → `staleness_thresholds`
(`flag_weeks`, `escalate_weeks`, `stale_mention_threshold`; shipped as 2 / 6 / 3).
Quote the configured values, never a remembered number.

**Level 1 (flagged — `flag_weeks`+ weeks stale):**
- State: "[Item] has been at [status] for [N] weeks without progress."
- Suggest: Check if the blocker is still valid. If yes, name the specific person to ping (look up `config/modules.json` → `categories` by module → `pm`; engineers are whoever `blocked_reason` names).

**Level 2 (escalated — `escalate_weeks`+ weeks stale OR high stale-mention ratio):**
- State: "[Item] has been stuck for [N] weeks. It's been mentioned in [M] pulse checks with progress in only [P]."
- Suggest one of:
  - **Escalate to PM** — if the blocker is a scope or priority decision
  - **Ping [specific engineer]** — if the blocker is technical and the person is named in `blocked_reason`
  - **Descope or backburner** — if the item has shown no movement since it escalated
  - **Close** — if the risk has been superseded by other work

## Step 3 — Write the priority dashboard

Write `outputs/priority-dashboard.md`:
```markdown
# Priority Dashboard — [DATE]

## Escalation Candidates

Items requiring action this week, ordered by composite score (priority × escalation).

| Item | Module | Score | Stale Weeks | Status | Recommended Action |
|------|--------|-------|-------------|--------|--------------------|
| [ONB-001] trial_started fires twice on mobile SDK retry | onboarding | 80 | 2 | active | Dedupe trial_started in acme_analytics.events for iOS builds |

## Blocked Longest

| Item | Module | Weeks Blocked | Blocker | Score |
|------|--------|---------------|---------|-------|
| [CHK-003] checkout step funnel gap | checkout | 4 | Missing step_viewed on plan picker (Eng) | 46 |

## Most Discussed Without Progress

| Item | Mentions | Progress | Gap | Score |
|------|----------|----------|-----|-------|
| [BIL-005] proration lines missing | 3 | 1 | 2 | 52 |

## Highest Priority Unactioned

| Item | Score | Stale Weeks | Status |
|------|-------|-------------|--------|
(Items with score > 60 and stale_weeks > 1)

## Cross-Module Signals

| Item | Primary Module | Also Affects | Score |
|------|---------------|--------------|-------|
| [ONB-002] anonymous_id → user_id bridge | onboarding | checkout | 58 |

## Full Backlog Snapshot

| Item | Module | Score | Status | Stale Wks | Esc |
|------|--------|-------|--------|-----------|-----|
(All active items sorted by priority_score DESC)
```

**Ordering for Escalation Candidates:**
Sort by `priority_score * (1 + escalation_level * 0.5)` descending. This surfaces moderately-important-but-very-stale items alongside critical-but-fresh items.

## Step 4 — Update last-run-summary

Update `data/state/last-run-summary.md` with a ~500 token narrative:
- How many active items across all categories
- Which items hit escalation thresholds this week
- Which items progressed vs. which are stalling
- Top 3 recommended actions for the week

## Step 5 — Present for review

**Do NOT write files yet.** Present the priority dashboard and all proposed frontmatter updates to the operator for review. On approval, write:
1. `outputs/priority-dashboard.md`
2. `data/state/last-run-summary.md`
3. Any backlog item files with updated `escalation_level`

## Staging mode (orchestrated runs)

When the invocation says **STAGING MODE** (or env `SIXEYES_STAGING=1`), this skill is
running inside `/six-eyes-run`. Do **not** present the Step 5 review gate and do **not**
update `data/state/workflow-state.json`. Instead write to the staging mirror:

1. priority dashboard → `data/staging/staged/outputs/priority-dashboard.md`
2. last-run-summary → `data/staging/staged/data/state/last-run-summary.md`
3. each backlog item with a changed `escalation_level` → full file to
   `data/staging/staged/data/backlog/<id>-<slug>.md`, editing any staged copy that
   already exists so changes accumulate.
4. Append a `## staleness-check` section to `data/staging/run-manifest.md`: items that
   crossed escalation thresholds this run, items that progressed vs. stalled, and the
   top 3 recommended actions.