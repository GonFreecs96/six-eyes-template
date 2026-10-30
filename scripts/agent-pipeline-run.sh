#!/bin/bash
# scripts/agent-pipeline-run.sh — Agent Pipeline Run (staging mode)
#
# Chains /agent-triage (incremental, staging) → /agent-work --checks (staging, only
# when checks are due) → up to 3 /agent-work [id] (staging) calls on the investigate
# steps, each a token-isolated `claude -p` invocation. Mirrors scripts/six-eyes-run.sh's
# pattern, scoped to the agent-workable-backlog lane. After this finishes, run
# `/agent-pipeline-run` for the consolidated review gate and promote on approval.
set -euo pipefail
cd "$(dirname "$0")/.."

STAGING="data/staging"
STAGED="$STAGING/staged"
MANIFEST="$STAGING/run-manifest.md"
BATCH_CAP=3
TRIAGE_BUDGET=2.50   # bumped from 2.00 2026-07-01: the real blocker wasn't the model
                     # pin or budget size — LOCAL_TOOLS lacked "Skill", so the
                     # "Run the X skill" prompt's Skill-tool call got silently denied
                     # and the agent fell back to a far pricier hand-reimplementation
                     # (confirmed via permission_denials in the JSON output). With
                     # Skill allowlisted, a full triage pass (25 items, all real work
                     # written: queue + 8 staged frontmatter changes) cost $2.0733 —
                     # a 3.6% near-miss of $2.00 from a trailing wrap-up turn, same
                     # pattern as the $1.50 cap before it. 2.50 gives that turn room.
                     # Incremental triage (the default here) normally costs far less.
CHECKS_BUDGET=1.00   # Due-checks step: read-only Jira/Confluence lookups, batched. Runs
                     # only when the staged queue reports checks due.
PER_ITEM_BUDGET=1.25 # One investigate step per item, up to BATCH_CAP items.
                     # Worst case total: 2.50 + 1.00 + 3*1.25 = 7.25; tune after real runs.

echo "=== Agent Pipeline Run (staging) ==="
echo "Started: $(date)"

# Preflight (binary lookup + live auth check) — fail fast BEFORE staging is cleared.
source scripts/claude-preflight.sh

if [ -d "$STAGING" ]; then
  echo "Clearing previous staging area ($STAGING)…"
  rm -rf "$STAGING"
fi
mkdir -p "$STAGED"

{
  echo "# Agent Pipeline Run Manifest — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "Each section below is a set of PROPOSED changes staged under \`$STAGED/\`."
  echo "Nothing has been promoted to its final location yet. Review with \`/agent-pipeline-run\`."
  echo ""
} > "$MANIFEST"

# Sync before triage, so triage's incremental selection sees the live metadata.
# (Triage skips its own sync in STAGING MODE.)
python3 scripts/sync-metadata.py

# Export so each skill can detect staging mode without relying solely on the prompt.
export SIXEYES_STAGING=1
export SIXEYES_STAGED_DIR="$STAGED"
export SIXEYES_MANIFEST="$MANIFEST"

# Skill must be on the allow list: the run_step prompts say "Run the X skill",
# so the agent naturally reaches for the Skill tool. Without it here, that call
# is not pre-approved (--allowedTools is an allow list, and -p mode has no prompt to approve it) and the agent falls back to
# hand-reimplementing the skill via Read/Write/Edit/Bash — far more turns/tokens
# than just invoking it (observed: a triage run hit error_max_turns at $1.96/20
# turns after exactly this denial).
# Grep,Glob added with the next-step rework: the skills search the backlog and
# warehouse-knowledge files, so they must be on the allow list too.
LOCAL_TOOLS="Read,Write,Edit,Bash,Skill,Grep,Glob"

# Checks step: local tools plus the read-only Atlassian lookups that `--checks` uses.
# No Atlassian write tools are listed, so a check cannot write to Jira or Confluence.
# --allowedTools is an allow list only. It does NOT stop a step from using other tools,
# so every step also gets an explicit DENY_TOOLS list via --disallowedTools: the Atlassian
# and Slack write/send tools. Confirmed against `claude --help`: --disallowedTools takes a
# comma- or space-separated list of tool names.
ATL="mcp__895f69c7-ac57-481d-983c-2083485b3062"
SLK="mcp__20369ed0-bc95-447b-9156-a036637c58d0"
DENY_TOOLS="${ATL}__editJiraIssue,${ATL}__addCommentToJiraIssue,${ATL}__transitionJiraIssue,${ATL}__createJiraIssue,${ATL}__addWorklogToJiraIssue,${ATL}__createIssueLink,${ATL}__updateConfluencePage,${ATL}__createConfluencePage,${ATL}__createConfluenceFooterComment,${ATL}__createConfluenceInlineComment,${SLK}__slack_send_message,${SLK}__slack_schedule_message,${SLK}__slack_send_message_draft,${SLK}__slack_create_canvas,${SLK}__slack_update_canvas"

CHECKS_TOOLS="$LOCAL_TOOLS,mcp__895f69c7-ac57-481d-983c-2083485b3062__getJiraIssue,mcp__895f69c7-ac57-481d-983c-2083485b3062__searchJiraIssuesUsingJql,mcp__895f69c7-ac57-481d-983c-2083485b3062__getConfluencePage,mcp__895f69c7-ac57-481d-983c-2083485b3062__searchConfluenceUsingCql"

run_step () {
  local label="$1" prompt="$2" tools="$3" turns="$4" budget="$5" out="$6"
  echo ""
  echo "--- $label ---"
  # A step hitting its budget/turn cap exits non-zero even when it finished its real
  # work. Don't let that abort the chain — record the gap in the manifest and keep
  # going so the review gate sees every step's output and the failure explicitly.
  # Pin the model explicitly — without this, claude -p inherits whatever model is
  # currently selected as the CLI default (observed: an unpinned run landed on the
  # 1M-context Opus variant, ~$2.47 for a single triage pass), making budget caps
  # meaningless. claude-sonnet-5 matches this session and is adequate for triage/work.
  if claude -p "$prompt" \
      --model claude-sonnet-5 \
      --allowedTools "$tools" \
      --disallowedTools "$DENY_TOOLS" \
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

# Render the agent queue as JSON (stdout), using the staged backlog as an overlay so
# earlier staged changes count. Renderer warnings go to stderr. Prints nothing on failure.
render_queue_json () {
  if [ -d "$STAGED/data/backlog" ]; then
    python3 scripts/render-agent-queue.py --json --overlay "$STAGED/data/backlog" || true
  else
    python3 scripts/render-agent-queue.py --json || true
  fi
}

# Print counts.checks_due from the queue JSON passed as $1 (0 if unparsable).
checks_due_count () {
  printf '%s' "$1" | python3 -c 'import json,sys
try:
    print(int(json.load(sys.stdin)["counts"]["checks_due"]))
except Exception:
    print(0)'
}

# Print the first $2 investigate item ids from the queue JSON passed as $1, in queue order.
investigate_ids () {
  printf '%s' "$1" | python3 -c 'import json,sys
cap = int(sys.argv[1])
try:
    rows = json.load(sys.stdin)["investigate"]
except Exception:
    rows = []
for r in rows[:cap]:
    print(r["id"])' "$2"
}

# Step 1: Agent Triage — incremental (items never assessed or touched since their
# last assessment), not --all. turns bumped 20->30 2026-07-13: hit error_max_turns at 21
# turns/$1.57 (well under the $2.50 budget) with a 45-item backlog (up from 25 at the
# last tuning pass) — 11 frontmatter diffs staged but the queue file itself never got
# written. Turns, not budget, was the binding constraint here, same shape as the
# six-eyes-run opportunity-scan/staleness-check turn-cap fixes.
run_step "Step 1: Agent Triage" \
  "Run the agent-triage skill INCREMENTALLY in STAGING MODE (not --all; see the skill's 'Staging mode' section). Do not present a gate; stage the queue + any frontmatter changes and append to the run manifest." \
  "$LOCAL_TOOLS" \
  30 "$TRIAGE_BUDGET" /tmp/agentpipeline-triage.json

# Step 2: Due checks — batched read-only Jira/Confluence lookups. Runs only when the
# staged queue reports checks due. A check that clears is promoted to its investigate
# step, so the investigate batch below is picked AFTER this step.
QUEUE_JSON=$(render_queue_json)
if [ -z "$QUEUE_JSON" ]; then
  echo "⚠️  Queue render failed after triage — checks and investigate batch will be skipped."
  {
    echo ""
    echo "## ⚠️ agent queue render failed"
    echo ""
    echo "\`scripts/render-agent-queue.py --json\` produced no output after triage. Checks and the investigate batch were skipped."
    echo ""
  } >> "$MANIFEST"
fi

CHECKS_DUE=$(checks_due_count "$QUEUE_JSON")
if [ "$CHECKS_DUE" -gt 0 ]; then
  run_step "Step 2: Due checks ($CHECKS_DUE)" \
    "Run /agent-work --checks in STAGING MODE (see the skill's 'Staging mode for --checks' section). Do not present a gate; stage each changed backlog file and append a '## agent-work --checks' section to the run manifest." \
    "$CHECKS_TOOLS" \
    25 "$CHECKS_BUDGET" /tmp/agentpipeline-checks.json
  # Re-render so promoted checks (new investigate steps) are included in the batch.
  QUEUE_JSON=$(render_queue_json)
else
  echo ""
  echo "--- Step 2: Due checks — none due, skipped ---"
  {
    echo ""
    echo "## agent-work --checks: none due"
    echo ""
    echo "The staged queue reported no checks due (recheck window not elapsed, or the queue render failed). Step skipped."
    echo ""
  } >> "$MANIFEST"
fi

# Pick the investigate batch: first BATCH_CAP ids in queue order (score DESC).
ITEM_IDS=()
if [ -n "$QUEUE_JSON" ]; then
  # Not `mapfile` — macOS ships bash 3.2 (no Homebrew bash installed here), and
  # mapfile is a bash 4+ builtin. `while read` is portable to 3.2.
  while IFS= read -r id; do
    if [ -n "$id" ]; then
      ITEM_IDS+=("$id")
    fi
  done < <(investigate_ids "$QUEUE_JSON" "$BATCH_CAP")
fi

if [ "${#ITEM_IDS[@]}" -eq 0 ]; then
  echo "No investigate steps in the queue — nothing to run through agent-work."
  {
    echo ""
    echo "## agent-work: none run"
    echo ""
    echo "The staged queue had no investigate steps (or the queue render failed). Batch skipped."
    echo ""
  } >> "$MANIFEST"
else
  echo "Queue picked up ${#ITEM_IDS[@]} item(s): ${ITEM_IDS[*]}"
  i=0
  for id in "${ITEM_IDS[@]}"; do
    i=$((i+1))
    run_step "Step 3.$i: Agent Work — $id" \
      "Run /agent-work $id in STAGING MODE (see the skill's 'Staging mode' section). Do not present a gate; stage the deep-dive + backlog step update and append to the run manifest." \
      "$LOCAL_TOOLS" \
      30 "$PER_ITEM_BUDGET" "/tmp/agentpipeline-work-$id.json"
  done
fi

echo ""
echo "=== Staging run complete: $(date) ==="
echo "Proposed changes staged under: $STAGED"
echo "Manifest: $MANIFEST"
echo ""
echo "Next: run /agent-pipeline-run to review the manifest and promote on approval."
echo "Total budget cap: \$$(python3 -c "print(f'{$TRIAGE_BUDGET + $CHECKS_BUDGET + $BATCH_CAP*$PER_ITEM_BUDGET:.2f}')")"
