---
name: opportunity-scan
description: Detect cross-module signals and update the cross-module registry.
allowed-tools:
  - Read
  - Write
  - Bash(python3:*)
---

# Skill: Opportunity Scan

## Purpose
Identify analytics items that span two or more modules (e.g. onboarding↔checkout, billing↔lifecycle, or a product module↔platform). Surface these so they get tracked once (not missed across modules or duplicated). Also flags items that have been stale but recently mentioned in a pulse check.

## Preprocessing
```bash
python3 scripts/sync-metadata.py
```

## Step 1 — Load active backlog items
Read all `data/backlog/*.md` files. Parse frontmatter for: `id`, `title`, `module`, `status`, `tags`, `cross_modules`.

## Step 2 — Cross-module tag matching
For each pair of items from different modules, check for:
- Shared tags (exact match)
- Title keyword overlap (3+ shared meaningful words, excluding stopwords)
- Explicit Jira ticket references appearing in both items' `links` frontmatter field

Score each pair:
- Shared tags: +2 per tag
- Title keyword overlap: +1 per word
- Shared Jira ticket: +3
- Threshold to flag: score ≥ 3

## Step 3 — Stale-but-mentioned detection
Query `metadata/sixeyes.db`:
```sql
SELECT id, title, module, stale_weeks, mention_count, progress_count
FROM items
WHERE status NOT IN ('backburner', 'done')
  AND stale_weeks >= 2
  AND mention_count > progress_count
ORDER BY (mention_count - progress_count) DESC
LIMIT 10;
```
These items are being discussed but not progressing — flag for review.

## Step 4 — Update cross-module registry
Read `data/signals/cross-module-registry.json` (create if missing with `{"links": [], "updated": null}`).

For each newly detected cross-module pair above threshold:
- Check if the pair already exists in the registry (by id_a + id_b)
- If new: add entry with today's date and confidence score
- If existing: update `last_confirmed` date

Write updated registry back to file.

## Step 5 — Output
```
## Opportunity Scan — [DATE]

### New cross-module signals
- [item-id-A] ([module]) ↔ [item-id-B] ([module]) — confidence [score]
  Overlap: [what they share]

### Stale-but-mentioned items
- [item-id] [title] — [stale_weeks]w stale, mentioned [N] times, [P] with progress
  Suggest: [escalate to PM | descope | schedule BQ audit | other]

### Registry update
[N] new links added. [M] existing links refreshed.
```

Present for review. Registry update writes proceed automatically (low-risk, no external side effects). Backlog item `cross_modules` frontmatter updates require confirmation.

## Staging mode (orchestrated runs)

When the invocation says **STAGING MODE** (or env `SIXEYES_STAGING=1`), this skill is
running inside `/six-eyes-run`. Do **not** auto-write the registry or present a gate,
and do **not** update `data/state/workflow-state.json`. Instead:

1. Write the proposed updated registry to
   `data/staging/staged/data/signals/cross-module-registry.json`.
2. For each backlog item whose `cross_modules` frontmatter you propose to change, write
   the **full updated file** to `data/staging/staged/data/backlog/<id>-<slug>.md`,
   editing any staged copy that already exists so changes accumulate.
3. Append a `## opportunity-scan` section to `data/staging/run-manifest.md`: new
   cross-module signals, stale-but-mentioned items, and registry links added/refreshed.
