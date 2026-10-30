# Overview — six-eyes-template

Public MIT template demonstrating Six Eyes patterns with **Acme** fictional data.

## Components

| Area | Path |
|------|------|
| Skills | `.claude/skills/` |
| Orchestration | `scripts/six-eyes-run.sh`, `scripts/six-eyes-promote.py` |
| Config | `config/runtime.yaml`, `config/modules.json` (SEED) |
| Demo data | `data/*` (SEED), `sample-inputs/*` (SEED) |
| Docs | `docs/ARCHITECTURE.md` |

## Stage 3 integration

- Run `scripts/export_context.py` after SEED fills `data/bq-knowledge.md`
- Regenerate `config/schemas/schema-meta.lock.json` via `check_schema_meta.py`
- Build explorer: `python scripts/build-explorer.py`
