---
name: backlog-prune
description: >
  Reconcile backlog staleness metadata against each item's Notes body, then
  classify genuinely dormant items for closure, stakeholder-pause, or an explicit
  decision from the operator. Two phases: Phase A fixes last_progress/last_touched drift
  via a deterministic
  script that auto-applies only unambiguous corrections; Phase B classifies true
  zombies once staleness is trustworthy. Never invents a stakeholder pause, never
  edits Notes prose or computed fields, never dispatches or publishes. On-demand;
  nudged when open items exceed ~50 or after an idle gap.
allowed-tools: Read, Edit, Bash(python3:*), Bash(sqlite3:*), Bash(grep:*)
---

## Purpose

`staleness-check` computes staleness. `close-loop` closes items whose investigation
finished. Neither handles the third case: an item that quietly stopped mattering, or
one whose staleness metadata is simply wrong.

> **"Which open items are actually dormant — and which just look dormant because
> their frontmatter drifted?"**

Escalation saturation often comes from backlog growth outpacing throughput.
Re-thresholding treats the symptom; pruning treats the source.

**Phase A is mandatory and runs first.** Pruning on bad staleness data is worse than
not pruning. If `last_progress` lags a recent Notes entry, an item can look like a
long-idle zombie while it was reactivated the same day — a prune keyed on `stale_weeks`
alone would propose closing live work.

## Invocation

```
/backlog-prune             # full run: reconcile, then classify
/backlog-prune reconcile   # Phase A only
/backlog-prune <ID>        # single item, both phases
```

## Boundaries

- **Never invents a stakeholder pause.** `backburner` means *explicitly
  deprioritized by a stakeholder*. Propose it only with quoted
  evidence from Notes or `blocked_reason`.
- **Never touches Notes bodies.** Notes are the source of truth; frontmatter is
  derived bookkeeping. Corrections flow body → frontmatter, never the reverse.
- **Never edits computed fields** (`stale_weeks`, `escalation_level`,
  `priority_score`). `sync-metadata.py` owns those and silently reverts hand-edits.
  Fixing `last_progress` is what makes them recompute correctly.
- **Never dispatches or publishes.** No Slack, Jira, email, Confluence.
- **Phase B status changes are per-item review-gated**, same as `close-loop`.

## Step 0 — Sync and scope

```bash
python3 scripts/sync-metadata.py
```

Scope is non-terminal items (`active`, `waiting`, `monitoring`). `done` and
`backburner` are already terminal — leave them alone.

## Phase A — Reconcile staleness truth

Extraction is **deterministic, in a script** — not model judgment. Freeform LLM
estimates of `stale_weeks` fight `sync-metadata.py`'s authoritative recompute;
date extraction by judgment reintroduces that failure mode.

```bash
python3 scripts/reconcile-progress-dates.py            # dry-run report
python3 scripts/reconcile-progress-dates.py --apply    # write unambiguous only
```

The script splits every in-scope item into two buckets:

| Bucket | Rule | Handling |
|---|---|---|
| **Unambiguous** | A full-ISO bold entry heading (`**2026-09-01 — …**`) at line start, newer than frontmatter, not a no-change annotation | **Auto-applied** by `--apply` |
| **Touch-only** | A `### 2026-09-01 — …` markdown heading (pulse-scan's per-mention style) newer than `last_touched` | `last_touched` auto-applied; the `last_progress` bump is listed for review (a mention isn't progress). Skipped entirely when `last_touched` already reflects it — the writer made the progress call then |
| **Needs review** | Month-name headings with no year (`**Jun 15 …**`), ISO dates appearing only in prose, a missing `## Notes` section, a future date, or a newest entry whose wording reads as "no change" | **Presented to the operator**, never auto-written |

Dates *inside* prose ("ACMECHK-138 updated 2026-07-22", "the Feb 3 freeze") are
references, not progress dates — the script matches heading position only. An item
is flagged for review only when there is real evidence the frontmatter is behind, so
the review list stays short enough to actually work through.

Run `--apply`, then present the review bucket as a table (item, current
`last_progress`, newest date seen, why it was deferred) and let the operator resolve each row
by hand with `Edit`. Then re-sync:

```bash
python3 scripts/sync-metadata.py
```

**Do not proceed to Phase B until Phase A is applied and re-synced** — Phase B's
candidate set is meaningless against uncorrected staleness.

## Phase B — Classify dormancy

Candidates, computed *after* reconciliation:

```sql
SELECT id, module, status, priority_score, stale_weeks,
       mention_count, progress_count, blocked_reason, last_progress
FROM items
WHERE status IN ('active','waiting','monitoring')
  AND stale_weeks >= 6
  AND priority_score < 55
  AND (mention_count - progress_count) <= 1
ORDER BY stale_weeks DESC;
```

`stale_weeks >= 6` matches `escalate_weeks` in `config/scoring-weights.json` — a
prune candidate should already be at escalation level 2 on time alone. Read the
threshold from config rather than hardcoding it if they ever diverge. Note that
`stale_weeks` counts **system-active weeks**, not calendar weeks, so an idle
gap does not manufacture candidates.

The other two filters are deliberately conservative — this skill should
under-propose. A high mention-gap means the system keeps seeing the item, which is
the opposite of dormant, and `sync-metadata.py`'s mention-gap override already
escalates it independently.

For each candidate, read the item file and classify into exactly one class:

| Class | Requires | Proposal |
|---|---|---|
| **Superseded** | Another item, a shipped feature, or a closed ticket demonstrably covers it — name it | → `done`, with the superseding reference added to Notes |
| **Stakeholder-paused** | Notes or `blocked_reason` records an actual person or decision pausing it | → `backburner`, quoting the evidence verbatim |
| **Blocker resolved** | `blocked_reason` names a trigger that has since fired | → **no status change**; recommend `/close-loop` or `/agent-work`. This is live work, not a prune |
| **Needs decision** | None of the above — genuinely just neglected | → **no status proposed.** Surface with a one-line question for the operator |

**Needs-decision is the honest default.** Do not route an item to `done` or
`backburner` to reduce the candidate count. An item nobody has decided about is
information about capacity, not a data-quality defect — and burying it destroys
exactly the signal Six Eyes exists to keep.

## Step 3 — Present and apply

One table per phase, each row independently approvable. Apply approved Phase B rows
with `Edit` (status + a dated Notes entry recording the reason), re-run
`sync-metadata.py`, and report:

- **Phase A** — items auto-applied, largest drift corrected, items left for review,
  resulting escalation-level shift
- **Phase B** — counts by class, items actually transitioned, items left as
  needs-decision

## Step 4 — Record the run

Append one entry to `data/state/workflow-state.json` `runs[]`:

```json
{
  "timestamp": "<ISO>",
  "workflow": "backlog-prune",
  "items_reconciled": ["ONB-001", "CHK-003"],
  "items_deferred_to_review": ["LIF-007"],
  "items_transitioned": {"BIL-005": "active -> done"},
  "items_needing_decision": ["PLT-009"],
  "notes": "<what drove the pass>"
}
```

## Rules

- **Reconcile before pruning.** Phase B against uncorrected staleness is invalid.
- **The Notes body outranks the frontmatter.** Frontmatter is derived bookkeeping.
- **Deterministic where it can be.** Date extraction is the script's job, not the
  model's. Judgment is for classification, where it is unavoidable.
- **Under-propose.** A missed zombie costs one dashboard row; a wrongly-closed live
  item costs the work.
- **Stay in lane.** Status and date frontmatter only — never scores, never computed
  fields, never Notes prose, never anything outbound.
