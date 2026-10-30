---
name: retro
description: >
  Backward- and inward-looking system retrospective. Reviews the run of weekly
  briefings, escalated items, and resolved items, then asks the meta-question the
  other skills don't: what should Six Eyes ITSELF change? Produces applyable,
  review-gated proposals across five buckets — CLAUDE.md edits, scoring-weight &
  staleness-threshold tuning (empirical, best-effort), new-skill / skill-change
  candidates, SKILL.md procedure fixes, and ARCHITECTURE roadmap upkeep — plus a
  recurring-patterns narrative. Standalone, on-demand, nudges monthly. Drafts only:
  never edits config or docs without per-bucket approval; never publishes; never
  dispatches; never touches the backlog's investigative state.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash(sqlite3:*)
  - Bash(python3:*)
  - Bash(python:*)
  - Bash(find:*)
  - Bash(date:*)
  - Bash(git diff:*)
  - Bash(git log:*)
---

# Skill: Retro (system retrospective & self-improvement)

## Purpose

The other Six Eyes skills look outward and forward. `weekly-brief` asks *"what do I
do this week?"*.
`/retro` asks the third question neither covers:

> **"Given how the last several weeks actually went — what should Six Eyes *itself*
> change?"**

It reasons over the system's own operating history (run records, pulse-mention time
series, escalations, resolutions) and proposes concrete, review-gated changes to the
system's configuration and instructions. It is the implementation of the "broader
retro habit" the architecture roadmap defers (`docs/ARCHITECTURE.md` → Roadmap) and the
time-gated scoring and threshold reviews, and it's the consumer that `close-loop` was instrumented for
("the `retro` skill to reason about throughput").

## Invocation

```
/retro            # run a full retrospective for the current ISO week
/retro <YYYY>-W<WW>   # run/redo a retro stamped to a specific week
/retro tune       # weight/threshold bucket only (the empirical scoring/threshold pass)
```

## Boundaries — what this skill NEVER does

These are non-negotiable and mirror the house rules:

- **Never publishes to Confluence** (no recurring publisher exists; one-offs are separately gated).
- **Never dispatches Slack / Jira / email** (that's `close-loop`, drafts-only).
- **Never touches the backlog's investigative state** — it does not change item
  statuses, scores, escalations, or notes. It proposes changes to *the system*, not
  to *the work*.
- **Never applies a config or doc edit without explicit per-bucket approval.** Every
  proposed diff is presented inline and applied only on a clear "yes" for that bucket.
- The retro document itself is written only after the operator approves it.

> Unlike `/six-eyes-run`, this skill does **not** use a `data/staging/` mirror. That
> mirror exists to survive headless, fresh-context pipeline steps. `/retro` runs in a
> single interactive context, so it presents diffs inline and applies them per-bucket
> on approval — simpler and equally safe.

## Step 0 — Cadence check

Find the most recent prior retro:

```bash
ls data/retros/*-retro.md 2>/dev/null | sort | tail -1
date +%G-W%V
```

- Derive the current ISO week as `YYYY-WWW` (e.g. `2026-W24`) — same scheme as
  `data/pulse-checks/` and `data/deep-dives/`. The output file is
  `data/retros/{YYYY}-W{WW}-retro.md`. If the operator passed an explicit week, use that.
- State how long since the last retro. If it's been **< 4 weeks**, say so and note
  that the empirical tuning bucket (2) will likely be thin — offer to run patterns +
  CLAUDE.md only, or proceed in full. If **≥ 4 weeks** (or no prior retro), proceed in
  full; this is the intended cadence.
- If a retro for this week already exists, this is a re-run: read it first and treat
  the new run as an update rather than starting blank.

## Step 1 — Gather the operating history (compressed sources only)

**Do NOT re-pull raw Jira or Slack.** Read only the compressed system state:

1. `data/state/run-archive.json` **plus** the `runs[]` array in
   `data/state/workflow-state.json` — together these are the ground truth for
   *what was actually worked on* (workflow-state keeps only the 3 most recent
   runs; `scripts/rotate-run-history.py` rotates the rest into the archive).
   Each entry has `item_id`, `workflow`
   (`close-loop` / `deep-dive` / `agent-work` / scan skills), `timestamp`,
   `status_transition`, `outreach_drafted`, `in_repo_applied`. Also read the per-skill
   `last_run` markers and `publish_*` markers.
2. `metadata/sixeyes.db` — query the **`pulse_mentions_weekly`** view (NOT the raw
   `pulse_mentions` table) for the week-by-week `had_progress` time series per item:
   weeks with two pulse files (e.g. a `-pulse.md` plus a module-specific sibling)
   produce two raw rows per item at the same `pulse_date`, and the view dedupes them
   via `MAX(had_progress) GROUP BY item_id, pulse_date` — raw `COUNT(*)` double-counts.
   Also query the **`score_history`** table (one snapshot per item per sync day:
   `priority_score`, the three dimensions, `stale_weeks`, `escalation_level`, `status`)
   for scores *as they were* at decision time — this removes the snapshot-vs-historical
   caveat that limits the empirical scoring/threshold passes before `score_history` exists. The
   **`items`** table remains the current snapshot (status, the three dimensions,
   `priority_score`, `escalation_level`, `mention_count`, `progress_count`,
   `stale_weeks`, `agent_next_step`, `agent_step_type`, `agent_step_check`, `agent_step_as_of`).
   If the DB is missing or stale, rebuild it first: `python3 scripts/sync-metadata.py`. A rising count
   of unassessed items is a routing-health signal worth surfacing. The checks-waiting count is
   informational only. Read both from `python3 scripts/render-agent-queue.py --json` (`counts`).
3. The run of recent **pulse checks** (`data/pulse-checks/`) and **weekly briefings**
   (`outputs/weekly-briefing.md` and any archived ones) since the last retro — read
   for recurring themes, not to re-derive facts.
4. **Backlog frontmatter** — scan for items that escalated (`escalation_level`
   increased / status → escalated) and items that resolved (status → done) in the
   window. Use the DB where possible; fall back to reading files.
5. **`data/bq-knowledge.md`** — note what's accumulated since the last retro; recurring
   gotchas are candidates for promotion into CLAUDE.md (bucket 1).
6. The current state of the four edit targets: `CLAUDE.md`,
   `config/scoring-weights.json`, the relevant `SKILL.md` files, and
   `docs/ARCHITECTURE.md` (Roadmap section).

Summarize the window up front in the retro doc: weeks covered, # runs by workflow type,
items escalated, items resolved, net backlog movement.

## Step 2 — Analyze the five buckets

Produce a proposal for each bucket. A bucket with nothing to propose is stated as
"No change proposed" with a one-line reason — never padded.

### Bucket 1 — CLAUDE.md edits
Look for: recurring `bq-knowledge.md` gotchas that have shown up enough to earn a place
in the always-loaded instructions; contact/role/module drift (people who left, PMs who
changed, channels that moved) visible in run history vs. the `pm` roster in `config/modules.json`; tables
or quick-reference rows that are now wrong. Output a concrete diff to `CLAUDE.md`.

### Bucket 2 — Scoring-weights & staleness-threshold tuning (empirical, best-effort)
Run the **scoring test**: *are high-`priority_score` items actually the ones that got
worked next?*

- "Worked next" = items whose backlog file got a **non-automated commit** in the window
  (`git log --since=… --no-merges --name-only -- data/backlog/`, excluding six-eyes-run /
  meeting-ingest / sync-metadata / agent-triage / rotate / ledger commits), cross-checked
  against `runs[]` investigative workflows (`deep-dive`, `agent-work`, `close-loop`) and
  `pulse_mentions_weekly.had_progress`. Exclude commits that only close or backburner an
  item — that's hygiene, not work. `runs[]` alone under-records investigative work
  that never logged a workflow run.
- Compare that set against current `priority_score` and the three dimension values.
  Are `priority_score > 60` items over-represented in worked items? Are there
  high-worked, low-score items (a sign a dimension is under-weighted) or high-score,
  never-touched items (over-weighted)?
- Run the **threshold test**: did escalations (`escalation_level` bumps) feel
  right, or was the system too noisy / too quiet? Baseline is whatever
  `config/scoring-weights.json` currently holds — read it, don't assume defaults.
- **Check for saturation, not just individual bumps.** If a large share of non-terminal
  items sit at `escalation_level` 2, the field has stopped discriminating regardless of
  whether each bump was individually defensible. Query the *distribution over time* from
  `score_history`, and look for bumps clustered on a single `snapshot_date` — a cluster
  means a cohort crossed a threshold together (usually because the system itself was
  idle), not that N independent risks materialized. `stale_weeks` counts system-active
  weeks (weeks with a pulse-check), which damps this but does not eliminate it.

> **Coverage caveat.** When `score_history` exists, prefer scores *as they were* at
> decision time. Older windows may lack history or pulse-mention coverage (weeks with
> no pulse-check are absent). State the sample size; if the signal is weak, propose
> **no weight change** rather than tuning on noise.

Output: a diff to `config/scoring-weights.json` (weights and/or thresholds) **only** if
the evidence supports it, with the supporting numbers shown.

### Bucket 3 — New-skill / skill-change candidates
Look for recurring *manual* investigation shapes across the run history and deep dives —
the same kind of ad-hoc work done repeatedly that a skill could codify. Respect the
existing boundary that exploratory/T3 work stays in the raw `bigquery` skill and
governance is for repeatable T2 metrics — propose a new skill only when the pattern is
genuinely repeatable and well-specified. Output: prose proposal (name, trigger,
inputs/outputs, why now), not a diff.

### Bucket 4 — SKILL.md procedure fixes
From the run history, find steps in existing skills that are consistently corrected,
skipped, or worked around (e.g. a check that always has to be redone, an instruction
that's regularly overridden). Output a diff to the specific `SKILL.md`.

### Bucket 5 — ARCHITECTURE roadmap upkeep
Keep `docs/ARCHITECTURE.md` honest: mark deferred items that have shipped as
IMPLEMENTED, retire items that are dead, and add newly-surfaced deferred items
(including any from the bucket-2 caveat). Output a diff to `docs/ARCHITECTURE.md`.

### Recurring-patterns narrative
A short prose section synthesizing cross-week themes that feed buckets 3–5: a module
perpetually at risk, a signal source that's reliably noisy or reliably silent, a class
of item that always goes stale. This is the connective tissue, not a sixth diff.

## Step 3 — Write the retro doc (after approval)

Present the full analysis in-conversation first. On the operator's approval, write
`data/retros/{YYYY}-W{WW}-retro.md`:

```markdown
# Six Eyes Retro — {YYYY}-W{WW}

**Window:** {first week} → {this week} ({N} weeks since last retro)
**Activity:** {runs by workflow type} · {items escalated} · {items resolved} · {net backlog movement}

## Recurring patterns
{narrative}

## Proposals

### 1. CLAUDE.md
{summary + the diff, or "No change proposed — {reason}"}

### 2. Scoring-weights & thresholds
{the scoring/threshold numbers, the caveat, the diff or "No change proposed — {reason}"}

### 3. New-skill / skill-change candidates
{prose proposals, or "None this cycle"}

### 4. SKILL.md procedure fixes
{summary + diff, or "No change proposed — {reason}"}

### 5. ARCHITECTURE roadmap
{summary + diff, or "No change proposed — {reason}"}

## Decisions
{filled in at Step 4 — which buckets were applied, deferred, or rejected}
```

## Step 4 — Per-bucket approval & apply

For each bucket with a proposed diff, ask explicitly and apply only on a clear yes:

> **"Apply bucket 1 (CLAUDE.md)? — yes / no / edit"**

- `yes` → apply the diff to the target file with Edit.
- `edit` → revise the proposal per the operator's feedback, re-present, re-ask.
- `no` → record as deferred/rejected with the reason.

Apply buckets independently — approving config tuning doesn't imply approving a
CLAUDE.md edit. After the apply pass, fill in the **Decisions** section of the retro doc
with what was applied / deferred / rejected, and write the doc.

## Step 5 — Record the run

Append one entry to `data/state/workflow-state.json` `runs[]`:

```json
{
  "timestamp": "<ISO>",
  "workflow": "retro",
  "week": "{YYYY}-W{WW}",
  "buckets_applied": ["scoring-weights", "architecture"],
  "buckets_deferred": ["claude-md"],
  "retro_doc": "data/retros/{YYYY}-W{WW}-retro.md"
}
```

If any applied change touched files that feed the metadata index, re-sync:

```bash
python3 scripts/sync-metadata.py
```

Then report a one-paragraph summary: what was reviewed, what changed, what was deferred,
and when the next retro is due (~4 weeks out).

## Rules

- **Compressed sources only** — never re-pull raw Jira/Slack; reason over state, pulse
  mentions, run history, and the doc/config targets.
- **Drafts until approved** — present every diff inline; apply per-bucket on explicit
  approval; write the retro doc only after approval.
- **No tuning on noise** — if the empirical window is thin or the signal weak, propose
  no weight change and say why. State the history-coverage caveat that actually applies
  (see bucket 2) — not the retired snapshot-vs-historical one.
- **Stay in lane** — propose changes to the *system* (config, instructions, roadmap),
  never to the *work* (backlog items, statuses, scores) and never anything outbound.
- **Empty buckets are stated, not padded** — "No change proposed — {reason}" beats
  invented churn.
