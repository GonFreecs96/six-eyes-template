# Governed repo bridge

Six Eyes can optionally mirror validated warehouse notes into a **sibling governed metrics repository** (your team's metric catalog / guardrails repo).

## Configuration

- `config/runtime.yaml` → `governed_repo: /absolute/path` or `null`
- Environment: `export GOVERNED_REPO=/path/to/repo`

When unset, promotion still writes a **local plan** under `outputs/governed-promotion/` and appends to `data/release-ledger/events.yaml`.

## Workflow

1. Curate rules in `data/bq-knowledge.md` (tagged ctx entries).
2. Run `python scripts/governed_knowledge_promote.py` (privacy pass + plan JSON).
3. Human review → manual PR into governed repo (automation roadmap).

## Local mirror (optional)

Clone your governed repo beside this template, e.g. `.tmp-governed/`, for read-only metric discovery (`repo-sync` skill). Do not commit clones.
