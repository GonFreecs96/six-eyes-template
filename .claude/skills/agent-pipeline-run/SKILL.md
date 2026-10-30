---
name: agent-pipeline-run
description: >
  Standalone orchestrated run: incremental /agent-triage → due /agent-work --checks
  (only when checks are due) → top 3 investigate steps by queue order via /agent-work
  [id], each in a token-isolated claude -p step (staging mode) via
  scripts/agent-pipeline-run.sh, then ONE consolidated review gate mirroring six-eyes-run.
  Batch cap: top 3 investigate steps per run, ~$7 worst-case total budget. close-loop
  stays a separate, deliberate per-item step — this skill never dispatches outbound
  messages and never publishes to Confluence.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(bash:*)
  - Bash(python3:*)
  - Bash(find:*)
  - Bash(cp:*)
  - Bash(mkdir:*)
  - Bash(rm:*)
---

# Skill: Agent Pipeline Run

## Purpose
Collapse the agent-next-step shuffle (`/agent-triage`, then a manual round of due
`/agent-work --checks`, then `/agent-work [id]` calls) into one command with one review
gate — same pattern as `/six-eyes-run`, scoped to the agent-step lane. `/agent-triage`
records each item's next step; the due checks promote any cleared check to its
investigate step; this skill then runs `/agent-work` on the top of the investigate queue,
batched, before the operator reviews anything.

> This skill never dispatches outbound messages (Slack/Jira/email) and never
> publishes to Confluence. `/close-loop` remains a separate, deliberate per-item
> step — outreach drafting shouldn't be batch-generated. Standalone cadence: NOT
> chained after `/six-eyes-run`, no scheduled cadence.

## Invocation
```
/agent-pipeline-run            # review the staged run and promote on approval
/agent-pipeline-run promote    # skip straight to promote (manifest already reviewed)
/agent-pipeline-run discard    # clear the staging area without promoting
```

## Step 0 — Staleness notice (soft, non-blocking)
Before running (or offering to run) the pipeline, check `data/state/workflow-state.json`
`last_run` against today. If the most recent pulse/staleness run is more than ~2 weeks
old, surface a one-line notice: "Priority scores may be stale — last full run was
[date]; consider `/six-eyes-run` first." Do not block on this — proceed either way if
the operator says to.

## Step 1 — Ensure a staged run exists
Check for `data/staging/run-manifest.md`.
- **If it exists:** go to Step 2.
- **If not:** offer to run it now:
  ```bash
  bash scripts/agent-pipeline-run.sh
  ```
  This runs, in order:
  1. `agent-triage` (staging, incremental — items never assessed or touched since their
     last assessment; not `--all`).
  2. `agent-work --checks` (staging), only if the staged queue reports checks due.
  3. Up to 3 `agent-work [id]` (staging) calls on the top investigate steps, in queue order.

  Total budget cap ~$7 worst case (triage $2.50 + checks $1.00 + 3 × $1.25). Long-running;
  either run it here via Bash or tell the operator to run it in a terminal and re-invoke
  `/agent-pipeline-run` when it finishes. Do not fabricate a manifest.

For `/agent-pipeline-run discard`: `rm -rf data/staging/` and stop.

## Step 2 — Present the consolidated review gate
Read `data/staging/run-manifest.md` and present it as the single review block, in this
order:
1. **Triage** — items whose next step was set or re-confirmed, with any step-type changes.
2. **Checks** — its own section. A table with one row per checked item: id, check,
   evidence (cited field or comment), result (**positive** / **negative** / inconclusive),
   proposed change. Inconclusive is treated as negative. If no checks ran, say so.
   Positives promote to an investigate step; negatives only advance `agent_step_as_of`.
3. **Investigations** — which items were picked up (top 3 investigate steps from the
   queue, score order) and why. For each: the finding summary and the proposed
   frontmatter/Notes diff.
4. Any `bq-knowledge.md` additions.

Then walk the staged mirror and show the file → destination mapping, same table format as
`/six-eyes-run`:
```bash
find data/staging/staged -type f | sort
```
Note that `outputs/agent-work-queue.md` is a staged render, not a file to promote; it is
re-rendered from the live backlog after promote (Step 3).

**Do not promote anything yet.** Ask explicitly: **"Promote all staged changes? — yes /
no / show <file>"**. Honor partial approval (promote a subset).

## Step 3 — Promote (only on explicit approval)
Same mechanism as `/six-eyes-run`, except the staged queue render is skipped:
```bash
(
  cd data/staging/staged || exit 1
  find . -type f ! -path './outputs/agent-work-queue.md' ! -path './data/bq-knowledge.md' | while read -r f; do
    dest="../../../${f#./}"
    mkdir -p "$(dirname "$dest")"
    cp "$f" "$dest"
  done
)
```
The subshell keeps the working directory at the repo root for the sync and render below.
`data/bq-knowledge.md` is excluded from the copy: the staged file holds only the new
entries, and copying it would overwrite the ~210KB live file. Append instead:
```bash
if [ -f data/staging/staged/data/bq-knowledge.md ]; then
  { printf '\n'; cat data/staging/staged/data/bq-knowledge.md; } >> data/bq-knowledge.md
fi
```

Then re-sync and render the live queue from live files. Never copy the staged queue:
```bash
python3 scripts/sync-metadata.py && python3 scripts/render-agent-queue.py
```

## Step 4 — Write the run record
Read `data/state/workflow-state.json`, append one run entry (`workflow:
"agent-pipeline-run"`, the item IDs processed, checks run and their results,
`items_updated`, deep-dive files written). Write it after Step 3's sync and render.

## Step 5 — Clear staging and report
```bash
rm -rf data/staging
```
Report: items processed, checks run (positive / negative counts), findings in one line
each, step changes applied, total spend if available from the `claude -p` JSON outputs.
Remind the operator that each item's outbound handoff is a separate, deliberate `/close-loop [id]`
call — not run here.

## Notes
- Batch cap (top 3 investigate steps, ~$7 worst case) is a starting point — tune after
  2-3 real runs per the design brainstorm (`docs/workflow-brainstorm_2026-07-01.md`).
  The checks step only runs when something is due, so most runs cost less.
- If the investigate queue has fewer than 3 items, run only what's available — don't pad
  the batch with items that have no investigate step (`check` steps not yet due, no step,
  or unassessed).
- If an `agent-work` step in the chain fails or hits its budget cap, the manifest gap is
  surfaced the same way `/six-eyes-run` handles it — don't promote a partial finding
  silently.
- Reuses `/six-eyes-run`'s exact staging/promote/manifest mechanism (see that skill for
  the underlying convention) — this is a second, narrower application of the same
  pattern, not a fork of it.

## Never
- Never chain `/close-loop` — outreach drafting is a separate, deliberate per-item step.
- Never publish to Confluence.
- Never let a checks step write to Jira or Confluence — its tools are read-only.
- Never schedule this — manual-first, same as `/six-eyes-run`'s original phase.
- Never run more than the capped batch (default 3) without the operator explicitly raising it.
- Never let a step write to Jira, Confluence or Slack. Every `claude -p` step carries a
  `--disallowedTools` deny list (Atlassian write tools, Slack send/schedule/draft/canvas
  tools; see `DENY_TOOLS` in `scripts/agent-pipeline-run.sh`). `--allowedTools` alone is
  only an allow list and does not block other tools.
