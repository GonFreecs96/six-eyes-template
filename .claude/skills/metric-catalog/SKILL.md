---
name: metric-catalog
description: Discover governed metrics before writing raw warehouse SQL.
---

# metric-catalog

Before hand-writing SQL against `acme_analytics.*`, check whether a **governed metric** already answers the question.

## Steps

1. If `GOVERNED_REPO` / `.tmp-governed/` exists, search that repo's metric docs/skills for the concept (trial conversion, churn, MRR, etc.).
2. If a governed definition fits, cite it and prefer its filters/grain.
3. If none fit, proceed with explicit raw SQL via `bq_client.py` and note the catalog gap in backlog.

## Rules

- Do not duplicate full metric definitions into Six Eyes — link or name the governed artifact.
- Read-only on the governed mirror.
