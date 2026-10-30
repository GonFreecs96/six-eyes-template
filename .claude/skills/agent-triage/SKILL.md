---
name: agent-triage
description: >
  Record the single next agent-runnable step for each open backlog item, as frontmatter
  (agent_next_step / agent_step_type / agent_step_check / agent_step_as_of), then
  re-render the agent work queue. A step is a read-only action that produces new
  evidence (warehouse query, definition audit, or a read-only Jira/Confluence check).
  Triage only: it never runs BigQuery, analytics, Jira or Confluence itself, and never
  runs an investigation (that's /agent-work). Proposes frontmatter changes for review
  before writing.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(python3:*)
  - Bash(sqlite3:*)
---

# Skill: Agent Triage

## Purpose
Each open backlog item gets **one** next agent-runnable step, or `null` if there isn't
one. The step is the thing `/agent-work [id]` (investigate) or `/agent-work --checks`
(check) would do next. Triage decides *what the step is*; it does not run it.

A step is any read-only action that produces new evidence:
- **warehouse**: a BigQuery query, a governed metric, or a spine-backed analytics skill.
- **definition audit**: a read-only audit of your governed metrics repo (`GOVERNED_REPO` if set),
  `config/context/`, or `config/schemas/`.
- **precondition check** (`agent_step_type: check`): a read-only Jira/Confluence lookup that
  settles whether something has happened yet (e.g. a ticket shipped). A check always names
  the investigate step it promotes to, and that promote target must itself meet the
  concreteness bar.

Not steps: outreach, decisions or prioritisation only the operator or a stakeholder can make,
waiting with nothing checkable, writes to any external system, or re-running an analysis
whose inputs haven't changed. The rubric is `config/agent-workability.json`.

## Invocation
```
/agent-triage              # incremental: items never assessed, or touched since last assessed
/agent-triage --all        # full sweep of every non-done/backburner item (also the one-time migration)
/agent-triage [item-id]    # assess one item
```

## Step 0 — Load inputs and pick candidates
1. Run `python3 scripts/sync-metadata.py` so the index is current. **Skip this in STAGING MODE**:
   the pipeline syncs before triage.
2. Read `config/agent-workability.json` (the rubric: step sources, not_a_step, concreteness bar,
   checkpoint rule, check semantics).
3. Pick candidates from the metadata index. Dates are ISO text, so string comparison works.
   - Default (incremental):
     ```bash
     sqlite3 metadata/sixeyes.db "SELECT id, module, priority_score, status, agent_step_as_of, last_touched
       FROM items
       WHERE status NOT IN ('backburner','done')
         AND (agent_step_as_of IS NULL OR last_touched > agent_step_as_of)
       ORDER BY priority_score DESC;"
     ```
   - `--all` assesses every non-done/backburner item, in this order, and skips items whose
     `agent_step_as_of` is already today (so repeated `--all` runs walk the whole backlog):
     ```bash
     sqlite3 metadata/sixeyes.db "SELECT id, module, priority_score, status, agent_step_as_of, last_touched
       FROM items
       WHERE status NOT IN ('backburner','done')
         AND (agent_step_as_of IS NULL OR agent_step_as_of < '<TODAY>')
       ORDER BY agent_step_as_of IS NOT NULL, agent_step_as_of ASC, priority_score DESC;"
     ```
     Replace `<TODAY>` with the local date from `date +%F` (not SQLite's `date('now')`, which is UTC).
   - `[item-id]` assesses just that item.
4. Open **only** the candidate files (`data/backlog/[id]-*.md`). Never open the rest.
5. If there are more than **20** candidates, process the top **15** in that order and say how
   many remain. Running the skill again picks up the rest.

Comparison is day-granular: a same-day touch after triage isn't re-queued until the next touch.

## Step 1 — Decide each item's step
For each candidate, read:
- the frontmatter,
- the most recent `## Notes` entries,
- any plan / next-steps section,
- the newest linked deep-dive, if the Notes point at one.

Do not decide from the title alone.

Then decide one of three outcomes:
- **investigate**: a specific read-only analysis that produces findings. Set `agent_step_type: investigate`.
- **check**: a yes/no precondition test on something external (usually a Jira key). Set
  `agent_step_type: check`. Phrase the step as
  `Check <KEY> <what>: if <condition>, promote to: <investigate step>`, where the part after
  `promote to:` is itself a concrete, read-only investigate step that meets the concreteness bar
  (names a table, metric/skill, Jira key, or file path). A check whose promote target is vague
  is not a valid check; choose investigate-or-null instead.
- **null**: no step passes the bar. Set `agent_next_step: null`, `agent_step_type: null`.

Apply the bar from the rubric:
- `agent_next_step` must name at least one concrete target: an `acme_analytics.*`
  table, a registered metric or skill name, a Jira key `[A-Z]+-\d+`, or a repo / governed repo / dbt path.
  Reject vague steps at draft time.
- Apply `not_a_step`. If the only candidate is outreach, a decision, or uncheckable waiting, the answer is null.

**Checkpoint.** Set `agent_step_check` when a human must confirm a definition, segment, or
interpretation before the result can be trusted. Name the specific assumption. Don't hedge
generically. When unsure whether a checkpoint is needed, set one.

**Output per item.** Proposed fields plus a one-line reason citing the Notes text or frontmatter
field that drove the call.

**Good / bad examples** (step text is quoted in YAML):
- Good investigate: `"Audit governed repo trial_conversion_rate filter: does it exclude same-day cancels?"`
- Good check: `"Check ACMECHK-260 fixVersion: if deployed, promote to: count checkout_started without matching trial_started on acme_analytics.events for mobile web"`
- Bad check: `"Check ACMECHK-260: if deployed, promote to the sizing step"`.
- Bad: `"Dig into persistency"`, `"Look at checkout data"`, `"Follow up on the eligibility issue"`. These fail the concreteness bar.
- Null, correctly: an item whose only forward move is "ask the owner whether to ship" is outreach, so null. Name the reason.

When unsure between a step and null, prefer **null** and give the reason.

## Step 2 — Present for review (nothing written yet)
Show a compact table, one row per item:

| Item | Step type | Next step | Check | Reason |
|------|-----------|-----------|-------|--------|

Then the counts: investigate, check, null, and any items left for the next run. **Do not write
anything yet.**

## Step 3 — On approval
For each approved item, edit the frontmatter in place:
- set `agent_next_step`, `agent_step_type`, `agent_step_check`, and `agent_step_as_of: <today>`
  (quoted strings when set, `null` otherwise);
- remove the retired single-label line, `agent_workability:`, if present.

Do **not** touch `last_touched`, `last_progress`, or `## Notes`. Triage is not progress.
Never hand-edit `escalation_level`, `stale_weeks`, or `priority_score`. They are computed.

With `--all`, also remove any `agent_workability:` line from done/backburner files. Do not add
step fields to those files.

Then, in live mode:
1. `python3 scripts/sync-metadata.py`
2. `python3 scripts/render-agent-queue.py` (writes `outputs/agent-work-queue.md`)

**Post-approval message.** If this run set any new check steps, end with:
"N new check steps set. Run `/agent-work --checks all` to get their first lookup now; otherwise
the first lookup is after the 7-day recheck window."

## Staging mode (orchestrated runs)
Staging is opt-in. Use it only when invoked with **STAGING MODE**:
- Skip Step 0's sync (the pipeline syncs before triage).
- Stage each changed backlog file in full, using the **live file's exact basename**, under
  `data/staging/staged/data/backlog/`. The full file, not a diff; promote is a straight copy.
- Render the staged queue with the overlay:
  `python3 scripts/render-agent-queue.py --overlay data/staging/staged/data/backlog --out data/staging/staged/outputs/agent-work-queue.md`
- Append a `## agent-triage` section to `$SIXEYES_MANIFEST` (or `data/staging/run-manifest.md` if unset)
  summarising what changed.
- Do **not** run sync and do **not** write live files, including the live queue.

## Rules
- **Triage only.** Never run BigQuery, analytics, Jira or Confluence here. Findings are `/agent-work`'s job.
- The handoff is always human (`/close-loop`). A step describes the investigation, never the outreach.
- When unsure between a step and null, choose null and say why. When unsure about a checkpoint, set one.
- Never write before the Step 2 approval.
- Keep free-text YAML values double-quoted.
