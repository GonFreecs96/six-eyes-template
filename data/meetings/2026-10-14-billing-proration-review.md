---
title: "Billing proration line-item review"
date: 2026-10-14
attendees: ["Priya Nair <priya.nair@example.com>", "Riley Foster <riley.foster@example.com>", "Operator <operator@example.com>"]
source: granola-export
---

# Billing proration line-item review

## Notes

- Header-level invoice totals reconcile after ACMEBIL-52; line_items still missing `proration` rows on ~8% of upgrades post 2026-09-10.
- Finance OK with header reporting for October close; SKU-level deferred.
- Deep-dive query shared in BIL-005 notes.

## Actions

- Priya: prioritize ACMEBIL-58 for line-item backfill.
- Riley: add proration_rows_missing rule to schema meta after context export.
