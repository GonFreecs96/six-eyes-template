---
name: repo-sync
description: Clone or pull optional sibling repos (governed metrics, dbt) into local mirrors.
---

# repo-sync

Keeps read-only mirrors fresh for investigation skills. **Never edit mirrors from this skill.**

## Targets

| Alias | Local path | Purpose |
|-------|------------|---------|
| `governed` | `.tmp-governed/` or `$GOVERNED_REPO` | Governed metric catalog |
| `dbt` | `.tmp-acme-dbt/` | Optional `DBT_REPO` models (if configured) |

## Usage

```
/repo-sync governed
/repo-sync dbt
```

Report: branch, last commit date, files changed since last sync note in `data/state/governed-repo-watchlist.json` if present.
