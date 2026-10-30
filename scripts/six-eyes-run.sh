#!/bin/bash
# scripts/six-eyes-run.sh — orchestrated weekly run (staging mode)
#
# Chains the weekly skills as token-isolated `claude -p` invocations, each in a
# fresh context window. Every skill runs in STAGING MODE: it writes its proposed
# artifacts to data/staging/staged/<final-relative-path> and appends a summary
# block to data/staging/run-manifest.md — it does NOT write to final locations,
# does NOT touch workflow-state.json, and does NOT present its own review gate.
#
# After this script finishes, run `/six-eyes-run` in Cursor to see the single
# consolidated review gate and promote the staged changes on approval.
#
# Usage:
#   bash scripts/six-eyes-run.sh            # pulse → opportunity → staleness → brief
#   SIXEYES_INCLUDE_MEETINGS=1 bash scripts/six-eyes-run.sh   # also chain meeting-ingest inline (opt-in)
#
# Offline mode: set config/runtime.yaml mode: offline (or SIX_EYES_MODE=offline) so
# pulse-scan and meeting-ingest read fixtures under sample-inputs/ instead of MCP.
#
# Meeting-ingest is NOT chained inline by default. It is the heaviest, most variable
# step and can hit the budget cap mid-chain, truncating the steps after it. Run it as its own
# invocation — the `/meeting-ingest` skill — before or after this chain, and promote
# its staged annotations at the same gate.
set -euo pipefail
cd "$(dirname "$0")/.."

STAGING="data/staging"
STAGED="$STAGING/staged"
MANIFEST="$STAGING/run-manifest.md"

echo "=== Six Eyes v3 Orchestrated Run (staging) ==="
echo "Started: $(date)"

# Preflight (binary lookup + live auth check) — shared with agent-pipeline-run.sh.
# Fail fast, before anything is cleared (see scripts/claude-preflight.sh).
source scripts/claude-preflight.sh

# Fresh staging area each run — promote (or discard) before re-running.
if [ -d "$STAGING" ]; then
  echo "Clearing previous staging area ($STAGING)…"
  rm -rf "$STAGING"
fi
mkdir -p "$STAGED"

# Seed the manifest header.
{
  echo "# Six Eyes Run Manifest — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "Each section below is a set of PROPOSED changes staged under \`$STAGED/\`."
  echo "Nothing has been promoted to its final location yet. Review with \`/six-eyes-run\`."
  echo ""
} > "$MANIFEST"

# Pre-processing (read-only / index only — safe to run before the gate).
bash scripts/granola-sync.sh 14 2>/dev/null || echo "Granola sync skipped (check cache path)"
python3 scripts/sync-metadata.py

# Record the run base (start HEAD + run-start blobs of any dirty/untracked files) so
# the gate can detect files that change under us while the steps run. Staged copies
# are 30-60 min old by promote time; blind promote can silently revert concurrent
# edits to append-style files. Recorded
# AFTER sync-metadata.py above so its computed-field rewrites count as base, not drift.
python3 scripts/six-eyes-promote.py record-base

# Export so each skill can detect staging mode without relying solely on the prompt.
export SIXEYES_STAGING=1
export SIXEYES_STAGED_DIR="$STAGED"
export SIXEYES_MANIFEST="$MANIFEST"

# Tool allow-lists for the headless `claude -p` steps. These run non-interactively,
# so a tool not on the list is *silently denied* — there's no approval prompt. The
# skills stage files with bash (cp/mkdir/awk/jq/.venv python), often as compound
# `cd … && cp …` commands that prefix patterns like Bash(cp:*) can't reliably match,
# so we allow Bash unrestricted. These are first-party, token-isolated workflow
# skills operating only inside this repo; outbound reach is limited to the MCP tools
# explicitly listed for Step 1.
# Skill must be on the list too: the run_step prompts say "Run the X skill", so the
# agent naturally reaches for the Skill tool. Without it, that call is silently
# denied and the agent falls back to hand-reimplementing the skill via
# Read/Write/Edit/Bash — far more turns/tokens than just invoking it (observed in
# agent-pipeline-run.sh testing: this exact denial caused an error_max_turns miss).
LOCAL_TOOLS="Read,Write,Edit,Bash,Skill"
PULSE_TOOLS="$LOCAL_TOOLS,mcp__atlassian__*"

run_step () {
  local label="$1" prompt="$2" tools="$3" turns="$4" budget="$5" out="$6" model="${7:-claude-sonnet-5}"
  echo ""
  echo "--- $label ---"
  # A step hitting its budget/turn cap exits non-zero even when it finished its real
  # work (e.g. the budget error is reported at end_turn). Don't let that abort the
  # whole chain via `set -e` — record the gap in the manifest and keep going so the
  # review gate sees every step's output and the failure explicitly.
  # Pin the model explicitly — without this, claude -p inherits whatever model is
  # currently selected as the CLI default, which can silently land on a far pricier
  # variant and make the --max-budget-usd caps meaningless (observed in
  # agent-pipeline-run.sh testing: an unpinned run landed on the 1M-context Opus
  # variant, ~$2.47 for a single step vs. ~$1.54 pinned).
  if claude -p "$prompt" \
      --model "$model" \
      --allowedTools "$tools" \
      --max-turns "$turns" --max-budget-usd "$budget" \
      --output-format json > "$out"; then
    echo "$label complete."
  else
    local rc=$?
    local subtype
    subtype=$(python3 -c "import json;print(json.load(open('$out')).get('subtype','unknown'))" 2>/dev/null || echo "unknown")
    echo "⚠️  $label exited non-zero (rc=$rc, subtype=$subtype) — continuing pipeline; verify staged output at the gate."
    {
      echo ""
      echo "## ⚠️ $label — did not exit cleanly"
      echo ""
      echo "Exit code \`$rc\`, result subtype \`$subtype\`. Staged artifacts from this step may be partial — verify before promoting."
      echo ""
    } >> "$MANIFEST"
  fi
}

# Step 1: Pulse Scan
run_step "Step 1: Pulse Scan" \
  "Run the pulse-scan skill for ALL scan sources in config/modules.json (Onboarding, Checkout, Billing, Lifecycle, Platform) in STAGING MODE (see the skill's 'Staging mode' section). Do not present a gate; stage artifacts and append to the run manifest." \
  "$PULSE_TOOLS" \
  70 6.00 /tmp/sixeyes-pulse.json

# Step 2: Meeting Ingest — run SEPARATELY, not inline by default.
# Chained inline it repeatedly aborted on the budget cap and truncated the rest of
# the pipeline, so it now runs as its own `/meeting-ingest` invocation. Opt back into
# the inline behavior with SIXEYES_INCLUDE_MEETINGS=1.
if [ "${SIXEYES_INCLUDE_MEETINGS:-0}" = "1" ]; then
  run_step "Step 2: Meeting Ingest (inline, opt-in)" \
    "Run the meeting-ingest skill in STAGING MODE. Do not present a gate; stage annotations and append to the run manifest." \
    "$LOCAL_TOOLS" \
    15 2.00 /tmp/sixeyes-meetings.json
else
  echo ""
  echo "--- Step 2: Meeting Ingest — SKIPPED (run /meeting-ingest separately; see header) ---"
  {
    echo ""
    echo "## Step 2: Meeting Ingest — run separately"
    echo ""
    echo "Meeting-ingest is not chained inline by default (it can hit the budget cap mid-chain and truncate later steps). Run it as its own \`/meeting-ingest\` invocation and promote its staged annotations at this gate or separately."
    echo ""
  } >> "$MANIFEST"
fi

# Step 3: Opportunity Scan
# Turn and budget caps move together: raising only turns trades a turn-cap miss
# for a budget-cap miss. 25 turns / $2.75 is the lowest pair that reliably lets
# the registry output finish; the step looks complete but exits non-zero when
# it trips either cap.
run_step "Step 3: Opportunity Scan" \
  "Run the opportunity-scan skill in STAGING MODE. Stage the cross-module registry and any cross_modules frontmatter proposals; append to the run manifest." \
  "$LOCAL_TOOLS" \
  25 2.75 /tmp/sixeyes-oppo.json

# Step 4: Staleness Check — same cap rationale as Step 3; this step is token-heavy
# and lower budgets trip error_max_budget_usd even when the staged output is complete.
# Runs on Haiku: it is the most mechanical step of the chain — sync-metadata.py does
# the scoring math; the skill mostly stages the dashboard + escalation frontmatter
# from computed fields. If a run produces off-target escalation rationale, drop the
# 7th arg to fall back to the default model.
run_step "Step 4: Staleness Check" \
  "Run the staleness-check skill in STAGING MODE. Stage the priority dashboard and escalation frontmatter proposals; append to the run manifest." \
  "$LOCAL_TOOLS" \
  25 2.75 /tmp/sixeyes-stale.json claude-haiku-4-5-20251001

# Step 5: Weekly Brief
run_step "Step 5: Weekly Brief" \
  "Run the weekly-brief skill in STAGING MODE. Stage the weekly briefing; append to the run manifest." \
  "$LOCAL_TOOLS" \
  10 1.00 /tmp/sixeyes-brief.json

echo ""
echo "=== Staging run complete: $(date) ==="
echo "Proposed changes staged under: $STAGED"
echo "Manifest: $MANIFEST"
echo ""
echo "Next: run /six-eyes-run in Cursor to review the manifest and promote on approval."
echo "Total budget cap: \$11.50"
