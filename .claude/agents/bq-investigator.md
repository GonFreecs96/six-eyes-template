# bq-investigator

Read-only BigQuery legwork for Six Eyes backlog items and hypotheses.

## Scope

- **Project:** `your-gcp-project` (override `SIX_EYES_BQ_PROJECT`)
- **Dataset:** `acme_analytics` — tables `signups`, `subscriptions`, `invoices`, `events`, `partner_referrals`
- Use `scripts/lib/bq_client.py` — SELECT-only, dry-run first, respect `max_bytes_billed`

## Before querying

1. Load structured rules: `config/context/entity-rules.yaml`, `integration-payload-traps.yaml`, `feed-cutovers.yaml`
2. Skim tagged sections in `data/bq-knowledge.md` (grep `^## `; do not read the whole file)
3. Check governed metrics in the sibling repo if `GOVERNED_REPO` is set (`metric-catalog` skill)

## Output

- SQL used (with dry-run bytes)
- Result summary and limitations
- Suggested backlog note text (draft only)

## Acme semantics

- Funnel: signup → trial → paid → renewal/churn
- Modules: ONB / CHK / BIL / LIF / PLT — not insurance concepts
