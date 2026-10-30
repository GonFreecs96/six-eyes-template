# Six Eyes Template

A personal **analytics-intelligence workspace** as a Git repo: a scored backlog
of warehouse and instrumentation risks, weekly pulse scans over Jira and
meetings, staleness escalation, and a promotion path for validated warehouse
knowledge into a governed metrics repo. Markdown and YAML in `data/` are the
source of truth; a SQLite index, a Flask board and a static explorer are
derived from them. Claude Code skills do the reading and drafting; a human
promotes every staged change and sends every outbound message.

**Author:** Mark Reid. The company (Acme Stream Co., a consumer subscription
app), its partner Zanybyte, its people, tickets and numbers are fictional. This
is the scrubbed, open form of a private workspace; `scripts/scrub_check.py` is
the gate that keeps it that way.

## Five minutes, offline

Everything below runs with no `claude` binary, no BigQuery, no MCP. Python 3.9+.

```bash
git clone <your-fork> six-eyes-template && cd six-eyes-template
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

`requirements.txt` also pulls the BigQuery client and pandas for the live and
report paths; the offline run itself needs only `pyyaml`, `Flask`, `Markdown`
and `pytest`.

```bash
.venv/bin/python scripts/init-db.py            # metadata/sixeyes.db schema
.venv/bin/python scripts/sync-metadata.py      # score the 10 fixture items, index 2 pulses
.venv/bin/python scripts/render-agent-queue.py # the agent work queue, by score
.venv/bin/python scripts/build-explorer.py     # regenerate docs/six-eyes-explorer.html
scripts/backlog-board.sh start                 # Flask board on http://127.0.0.1:5151
```

What you are looking at:

- `sync-metadata.py` reads `data/backlog/*.md` frontmatter, computes
  `priority_score`, `stale_weeks` and `escalation_level` from
  `config/scoring-weights.json`, writes them back into the frontmatter, and
  rebuilds `pulse_mentions` from `data/pulse-checks/`. The weights and the
  staleness thresholds live in that one config file; the code has no defaults
  of its own.
- `stale_weeks` counts **system-active weeks**: weeks that produced a pulse
  file. An operator absence does not age the whole backlog.
- The board (`webapp/backlog_board/`) is table, kanban and detail views over
  the index, read-only except a Refresh button that re-runs the sync.
- The explorer (`docs/six-eyes-explorer.html`) is a self-contained snapshot
  page: architecture, skill catalog, scoring calculator, the backlog itself.

A demo **staged run** ships under `data/staging/` (`run-manifest.md` plus
`staged/`). The promote step is conflict-aware against the commit a run
started from, so on a fresh clone record that base first:

```bash
.venv/bin/python scripts/six-eyes-promote.py record-base
.venv/bin/python scripts/six-eyes-promote.py check     # 2 staged files, 0 conflicts
.venv/bin/python scripts/six-eyes-promote.py promote
```

Tests and the scrub gate:

```bash
.venv/bin/python -m pytest -q          # 94 tests, hermetic
.venv/bin/python scripts/scrub_check.py
```

## What needs Claude Code

The skills under `.claude/skills/` are the product; the scripts above are the
deterministic parts they lean on. Running a skill needs Claude Code (or Cursor
reading `AGENTS.md` and `.cursor/rules/`):

- **Weekly loop:** `/pulse-scan` → `/opportunity-scan` → `/staleness-check` →
  `/weekly-brief`, or all four as one staged run via `/six-eyes-run`
  (`scripts/six-eyes-run.sh`, headless `claude -p` steps, one review gate,
  then `six-eyes-promote.py`). `/meeting-ingest` runs on its own.
- **Investigation lane:** `/agent-triage` records one read-only next step per
  item; `/agent-work` executes it against BigQuery through
  `scripts/lib/bq_client.py` (dry-run, byte cap, SELECT-only guard);
  `/agent-pipeline-run` chains the two with a batch cap.
- **Handoff:** `/close-loop` drafts Slack, Jira and email text and never sends.
  A PreToolUse hook in `.claude/settings.json` asks before any Atlassian or
  Slack write; the headless orchestrators pass an explicit deny list.
- **Daily:** `/today`, `/status`, `/deep-dive`, `/storyteller`,
  `/voice-rewrite` (reads `SOUL.md`), `/retro`, `/backlog-prune`.
- **Hooks:** a `UserPromptSubmit` hook injects matching warehouse rules from
  `data/bq-knowledge.md` into every prompt; a `Stop` hook re-runs the sync.

In `mode: offline` (`config/runtime.yaml`, the default) the skills read Jira
and meeting fixtures from `sample-inputs/`. `mode: live` needs Atlassian,
Slack and Granola MCP servers (`.cursor/mcp.json` is a placeholder) and GCP
credentials for BigQuery.

## Pairing with kattfot

[`kattfot`](https://github.com/GonFreecs96/kattfot) is the governed side:
agents answer only through allow-listed metric definitions, with provenance
manifests and a hash-chained audit. Six Eyes is the intake side: it finds the
instrumentation gaps and warehouse gotchas that end up as rules.

What exists today:

- `config/runtime.yaml: governed_repo` (or `GOVERNED_REPO`) points at a
  sibling checkout. The `repo-sync` skill clones or pulls it; the
  `metric-catalog` skill reads its definitions before anyone writes raw SQL.
- `data/bq-knowledge.md` is the human-authored rule set.
  `scripts/export_context.py` renders it to `config/context/*.yaml`;
  `scripts/check_schema_meta.py` fails the build if the schema paraphrases
  drift from it.
- `scripts/governed_knowledge_promote.py` runs a privacy pass over the rules,
  writes a **promotion plan** to `outputs/governed-promotion/` and appends a
  ledger entry to `data/release-ledger/events.yaml`. With `governed_repo` set
  it lists suggested patch paths inside that repo. It opens no PR and writes
  nothing there.

What does not exist yet: a contract. Nothing pins the shape a plan must have
to the shape kattfot's catalog accepts, and no test on either side would fail
if one changed. That contract, with a fixture exercised by both test suites,
is the next step. Until then the pairing is a documented intent.

## Status and limitations

Worth stating plainly rather than discovering:

- **Prompt-driven versus code.** The skills are `SKILL.md` prose executed by
  a model; what they do on a given week depends on the model and the data.
  The code paths (scoring, active-week counting, pulse parsing, promote
  conflict detection, the context export and its drift check, the partner
  report, the scrub gate) are deterministic and are what the 94 tests cover.
  Nothing tests a skill end to end.
- **The numbers are fictional.** Ten backlog items, two pulses, six Jira
  fixtures, three meetings. Scores and escalations are real computations
  over invented inputs.
- **Placeholders are placeholders.** `your-gcp-project`, the all-zero
  Atlassian cloud id, `config/confluence-registry.yaml`, the MCP URLs in
  `.cursor/mcp.json` and the `reports/acme_referral_partner/scheduler/`
  files are shapes to fill in, not working endpoints.
- **The orchestrators are tuned for one operator.** Turn and budget caps in
  `six-eyes-run.sh` and `agent-pipeline-run.sh` fit a backlog of a few dozen
  items. Expect to retune them, and expect a headless step to exit non-zero
  when it trips a cap even though its staged output is complete.
- **MCP tool names are yours to set.** `agent-pipeline-run.sh` builds its
  allow and deny lists from `SIX_EYES_MCP_ATLASSIAN` and
  `SIX_EYES_MCP_SLACK`; a wrong prefix means the deny list matches nothing.
- **The scrub gate is a blocklist.** It catches the tokens it knows about,
  line by line. Review of new prose is still the control.
- **Per-item owner and intake fields are not modelled.** Items carry a module
  and a PM via `config/modules.json`, not an owner or a source of record.

## Layout

| Path | What |
|------|------|
| `data/backlog/` | One Markdown file per item; frontmatter holds the scores |
| `data/pulse-checks/`, `data/meetings/`, `data/deep-dives/`, `data/retros/` | Weekly artifacts |
| `data/bq-knowledge.md` → `config/context/` | Warehouse rules, human-authored then exported |
| `config/` | Modules, scoring weights, runtime mode, schemas |
| `scripts/` | Deterministic helpers and the two headless orchestrators |
| `.claude/skills/`, `.claude/commands/` | The skills and slash commands |
| `webapp/backlog_board/` | Flask board |
| `docs/ARCHITECTURE.md` | Layers, conventions, roadmap |

## License

MIT — see [LICENSE](LICENSE).
