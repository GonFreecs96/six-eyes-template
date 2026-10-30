---
name: six-eyes-run
description: >
  One-command orchestrated weekly run. Runs pulse-scan → opportunity-scan →
  staleness-check → weekly-brief, each in its own fresh context via
  scripts/six-eyes-run.sh (staging mode), then presents ONE consolidated review
  gate. meeting-ingest runs separately (its own /meeting-ingest invocation) —
  not chained inline — so its budget cap can't truncate the rest of the chain.
  On approval, promotes all staged changes to their final locations and writes
  the run record. Never publishes to Confluence and never sends any outbound message.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(bash:*)
  - Bash(python3:*)
  - Bash(git:*)
  - Bash(find:*)
  - Bash(cp:*)
  - Bash(mkdir:*)
  - Bash(rm:*)
---

# Skill: Six Eyes Run (orchestrated weekly run)

## Purpose
Collapse the weekly pipeline into **one command with one review gate**.
The heavy lifting (Jira/meeting scans, scoring, synthesis) happens in
token-isolated `claude -p` steps that write *proposals* into a staging mirror;
this skill is the single human checkpoint that reviews everything at once and
promotes it on approval.

> **This skill never publishes to Confluence and never sends Slack/Jira/email.**
> Outbound handoffs stay in `close-loop`.

## Invocation
```
/six-eyes-run            # review the staged run and promote on approval
/six-eyes-run promote    # skip straight to promote (manifest already reviewed)
/six-eyes-run discard    # clear the staging area without promoting
```

## Step 0 — Ensure a staged run exists

Check for `data/staging/run-manifest.md`.

- **If it exists:** a staging run is ready — go to Step 1.
- **If it does not exist:** the pipeline hasn't been run yet. Offer to run it now:
  ```bash
  bash scripts/six-eyes-run.sh
  ```
  This is long-running (four chained `claude -p` steps, total budget cap $10.25 — pulse
  $5.00, opportunity $1.50, staleness $2.75, brief $1.00). **meeting-ingest is not chained inline** —
  it can exhaust the budget mid-chain and truncate later steps, so run it as its own
  `/meeting-ingest` invocation before or after this chain and promote its staged
  annotations at the same gate. (Opt back into inline meeting-ingest with
  `SIXEYES_INCLUDE_MEETINGS=1`.) Either run it via Bash here, or tell the operator to run it in
  a terminal and re-invoke `/six-eyes-run` when it finishes. Do not fabricate a manifest.

For `/six-eyes-run discard`: `rm -rf data/staging/` and stop.

## Step 1 — Present the consolidated review gate

Read `data/staging/run-manifest.md` and present it **verbatim-ish** as the single
review block, lightly grouped by skill. Then enumerate exactly what will change on
promote — **with conflict detection** — by running:

```bash
python3 scripts/six-eyes-promote.py check
```

Each staged path maps to a final path by stripping the `data/staging/staged/`
prefix. Present the script's table so the operator sees every file that will be
created/overwritten:

| Staged file | → Final path | Action | Why |
|---|---|---|---|
| data/staging/staged/data/pulse-checks/2026-W24-pulse.md | data/pulse-checks/2026-W24-pulse.md | create | |
| data/staging/staged/data/backlog/ONB-010-….md | data/backlog/ONB-010-….md | overwrite | |
| data/staging/staged/data/bq-knowledge.md | data/bq-knowledge.md | CONFLICT-merge | changed since run start (committed) |
| data/staging/staged/outputs/priority-dashboard.md | outputs/priority-dashboard.md | CONFLICT-skip | changed since run start (uncommitted working-tree edit) |
| … | … | … | … |

**Conflicts.** Staged files are snapshots taken when the `claude -p` steps ran, often
30-60 min before this gate. `scripts/six-eyes-run.sh` records the run base in
`data/staging/run-base.json` (start HEAD + run-start blobs of any dirty/untracked
files). A staged file is a **CONFLICT** when its live file differs from its run-start
content — commits landed since the start HEAD *and* uncommitted working-tree edits
both count (also: created or deleted by someone else since the start). List every
CONFLICT explicitly at the gate, above the approval question, with what promote will
do about it:

- **`CONFLICT-merge`** — append-style files (`data/bq-knowledge.md`, `data/backlog/*.md`,
  whose `## Notes` / `## Meeting Notes` grow by appends): promote does a 3-way merge
  (`git merge-file live run-base staged`) instead of copying, so the concurrent
  change and the staged change both land.
- **`CONFLICT-skip`** — anything else (dashboard, pulse check, registry, …): promote
  leaves the live file untouched. Tell the operator; he can re-run the producing step, or
  `show <file>` and decide by hand.

If the check reports **no `run-base.json`** (a run started before this hardening, or
the file was deleted), conflict detection is unavailable: say so, and diff every
`overwrite` against HEAD (`git diff --no-index <final> <staged>`) before asking to
promote.

Call out anything notable: new backlog items, status/escalation transitions,
proposed `bq-knowledge.md` additions, cross-module registry changes.

**Do not promote anything yet.** Ask explicitly: **"Promote all staged changes? — yes / no / show <file>"**.
`show <file>` reads and displays a staged file's full content. `no` leaves staging
intact for inspection and ends the run.

## Step 2 — Promote (only on explicit approval)

Never blind-`cp` the staged tree — concurrent edits to append-style files (for example
`data/bq-knowledge.md`) can be lost without merge-aware promote.
Promote through the script, which re-checks every file at promote time (so a change
that landed *during* the gate is still caught):

```bash
python3 scripts/six-eyes-promote.py promote
# subset approval: python3 scripts/six-eyes-promote.py promote --only data/backlog/CHK-004-….md outputs/priority-dashboard.md
```

Per file:
- **Not conflicted** → copied to its final path (parent dirs created) — unchanged behaviour.
- **`CONFLICT-merge`** → `git merge-file -p live run-base staged`. A clean merge is written
  to the live path. Conflict hunks consisting *only* of computed frontmatter fields
  (`escalation_level` / `stale_weeks` / `priority_score`) resolve to the live side —
  `sync-metadata.py` recomputes them in Step 3 anyway. Any other conflict hunk leaves
  the live file **untouched** and writes the conflict-marked result to
  `data/staging/conflicts/<path>`; show the operator those hunks and resolve them with him
  by hand-editing the live file (Edit tool).
- **`CONFLICT-skip`** → live file untouched; report it.

The script exits `2` when anything needs the operator's attention. Relay its result table,
and before committing, `git diff` every promoted overwrite as a final check. Do not
use `git checkout -- <file>` to recover a bad promote (the auto-mode classifier
blocks it) — restore with `git show HEAD:<file> > <file>` or re-apply the lost lines
with Edit.

If `run-base.json` is missing, `promote` refuses. Only after diffing every overwrite
by hand (Step 1) and the operator approving, re-run with `--allow-no-base` for the legacy
blind copy.

## Step 3 — Write the consolidated run record

The individual skills do **not** touch `data/state/workflow-state.json` in staging
mode — this skill owns the single state update. Read the current
`workflow-state.json`, then append one run entry summarizing the orchestrated run
(timestamp, `workflow: "six-eyes-run"`, the sub-skills that ran, `items_updated`,
`items_created`, pulse-check filename) and refresh the per-skill `last_run` markers
(`last_run`, `meeting_ingest_last_run`, etc.) from the manifest. Re-sync the index:

```bash
python3 scripts/sync-metadata.py
```

`data/state/last-run-summary.md` is promoted from staging like any other artifact
(staleness-check stages it) — do not regenerate it here.

## Step 4 — Clear staging and report

Keep `data/staging/` while any `CONFLICT-skip` or unresolved merge from Step 2 is
still open (the staged copies and `data/staging/conflicts/` are the only record of
the proposed change). Once every flagged file is resolved or the operator drops it:

```bash
rm -rf data/staging
```

Report: files promoted, new/updated backlog items, escalations raised this run, and
the top 3 recommended actions (lifted from the promoted weekly briefing). Note: the
loop is deliberately slim: pulse-scan, `/today`, promotion. This orchestrator never
publishes to Confluence or sends outbound messages.

## Notes
- The script clears and rebuilds `data/staging/` on each run, so a stale manifest
  is never silently reused — but if the operator edited staged files by hand, respect them.
- A standalone `/meeting-ingest` staged after `six-eyes-run.sh` started is covered by
  the same `run-base.json` (its base is the run start — older than its snapshot, so
  identical changes on both sides merge cleanly). One staged *before* the script ran
  is wiped by the script's fresh-staging step, as before.
- If a `claude -p` step failed mid-run, its section may be missing from the
  manifest. Surface that gap rather than promoting a partial run silently.
