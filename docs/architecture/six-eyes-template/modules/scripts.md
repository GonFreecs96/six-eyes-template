# Module: scripts

## Orchestration

- `six-eyes-run.sh` — headless skill chain → staging
- `six-eyes-promote.py` — conflict-aware promote
- `sync-metadata.py` — priority_score / staleness recompute

## Context / CI

- `export_context.py`, `check_schema_meta.py`, `check_context_sync.sh`

## Warehouse

- `lib/bq_client.py` — read-only BigQuery
- `claude-hooks/inject-bq-context.py` — prompt injection

## Governed promotion

- `governed_knowledge_promote.py` — local plan + ledger

## Utilities

- `init-db.py`, `build-explorer.py`, `backlog-board.sh`, `granola-sync.sh`
