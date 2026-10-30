# Six Eyes — Acme template harness

Personal analytics intelligence for a fictional consumer subscription company (**Acme**). Markdown + YAML in Git is the source of truth; agents assist with read-only warehouse checks and **draft** outbound handoffs.

## Modules (product areas)

| Module | Backlog prefix | Jira project (live mode) |
|--------|----------------|---------------------------|
| Onboarding | ONB | ACMEONB |
| Checkout | CHK | ACMECHK |
| Billing | BIL | ACMEBIL |
| Lifecycle | LIF | ACMELIF |
| Platform / analytics eng | PLT | ACMEPLT |

Funnel: signup → trial → paid subscription → renewal / churn.

## Runtime

- `config/runtime.yaml` — `mode: offline|live`, BigQuery placeholders, optional `governed_repo`.
- Offline fixtures: `sample-inputs/jira/*.json`, `sample-inputs/meetings/*.md`.
- Env overrides: `SIX_EYES_MODE`, `SIX_EYES_BQ_PROJECT`, `SIX_EYES_BQ_DATASET`, `GOVERNED_REPO`.

## BigQuery (read-only)

- Project: `your-gcp-project`, dataset: `acme_analytics`.
- Placeholder tables: `signups`, `subscriptions`, `invoices`, `events`, `partner_referrals`.
- Use `scripts/lib/bq_client.py` (dry-run, byte cap, SELECT-only guard). Agent: `.claude/agents/bq-investigator.md`.

## Skills (`.claude/skills/`)

Weekly orchestration: `six-eyes-run`, `pulse-scan`, `meeting-ingest`, `opportunity-scan`, `staleness-check`, `weekly-brief`.

Investigation: `deep-dive`, `agent-triage`, `agent-work`, `agent-pipeline-run`, `metric-catalog`.

Handoff: `close-loop` (draft Slack/Jira/email only — **never send**).

Local UI: `backlog-board`. Voice: `voice-rewrite`, `storyteller` (read `SOUL.md`).

## Rules

1. **Draft before write** on outbound systems; PreToolUse hook asks on Slack/Jira/Confluence writes.
2. **Orchestrated `/six-eyes-run`** writes to `data/staging/` until promote; one human gate via `scripts/six-eyes-promote.py`.
3. **Context layer:** edit tagged rules in `data/bq-knowledge.md`, run `scripts/export_context.py`; Confluence registry is `config/confluence-registry.yaml` (placeholder).
4. No insurance-domain examples in this template — Acme subscription semantics only.

## Commands

- `/today`, `/status` — `.claude/commands/`

## Index

- Architecture: `docs/ARCHITECTURE.md`
- Governed repo promotion: `docs/governed-knowledge-promotion.md`
