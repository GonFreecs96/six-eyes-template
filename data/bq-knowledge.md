---
title: BQ Findings Log
description: Running log of confirmed BigQuery schema facts, join patterns, and gotchas for Acme Stream Co.
last_updated: 2026-10-16
last_audit: 2026-09-20
---

# BQ Findings Log

Durable record of non-obvious warehouse facts for the Acme subscription app. Each entry links to a backlog item where possible.

**Structured export.** Tag rule-like entries with `<!-- ctx: ... -->`; run `python3 scripts/export_context.py` to refresh `config/context/*.yaml`.

---

## Core tables

| Table | Notes |
|---|---|
| `your-gcp-project.acme_analytics.signups` | One row per signup attempt. `anonymous_id` is the browser cookie; `user_id` is NULL until account creation completes. **Do not join subscriptions on anonymous_id after account linking** — use `user_id`. **Source:** ONB-001, 2026-08-14. <!-- ctx: id=signup_user_id_anchor entity=signup category=entity_rule cols=user_id,anonymous_id --> |
| `your-gcp-project.acme_analytics.events` | Client and server events. `event_name = 'trial_started'` can fire twice within 60s when the mobile SDK retries — dedupe on `(user_id, DATE(event_ts), event_id)` not raw row count. **Source:** ONB-001, 2026-09-02. <!-- ctx: id=trial_started_double_fire entity=event category=entity_rule cols=event_name,event_id,event_ts,user_id --> |

- **Upgrade-path step keys (events table).** Rows with event name `step_viewed` carry a `step_key` inside JSON properties. Legacy keys `plan_review` and `wallet_entry` were merged to `combined_step` in app v3.4; queries before 2026-09-01 must map old keys. **Source:** CHK-003, 2026-09-18. <!-- ctx: id=funnel_step_rename_cutover entity=funnel category=entity_rule cols=event_name,properties -->
| `your-gcp-project.acme_analytics.subscriptions` | `status` is point-in-time; `status_history` JSON array holds transitions. For churn analysis, prefer unnesting history rather than filtering current status only. **Source:** LIF-007, 2026-08-22. <!-- ctx: id=subscription_status_history entity=subscription category=entity_rule cols=status,status_history --> |
| `your-gcp-project.acme_analytics.invoices` | Amounts are **integer cents** in `amount_cents` and `line_items[].amount_cents`. Dashboards that divide by 100 are correct; do not double-convert. **Source:** BIL-005, 2026-08-05. <!-- ctx: id=invoice_amount_cents entity=invoice category=entity_rule cols=amount_cents,line_items --> |
| `your-gcp-project.acme_analytics.invoices` | Mid-cycle plan changes should produce `line_type = 'proration'` rows. After the 2026-09-10 billing deploy, ~8% of upgrades lack proration lines (invoice totals still correct). **Source:** BIL-005, 2026-09-12. <!-- ctx: id=proration_rows_missing entity=invoice category=entity_rule cols=line_type,invoice_id --> |
| `your-gcp-project.acme_analytics.partner_referrals` | Partner click id `ref_click_id` attributes to signup within **7 days** in product; warehouse `attribution_window_days` column defaults to 7 but Zanybyte feed uses 14 for podcast campaigns. **Source:** PLT-009, 2026-10-01. <!-- ctx: id=partner_attribution_window entity=partner category=integration_payload_trap cols=ref_click_id,attribution_window_days,partner_code --> |
| `your-gcp-project.acme_analytics_staging.stg_lifecycle_churn_feed` | Nightly churn-reason feed; `churn_reason_code` NULL for rows after 2026-09-25 when `feed_version` bumped to 3 without backfill. **Source:** LIF-007, 2026-09-28. <!-- ctx: id=churn_reason_null_feed entity=subscription category=entity_rule cols=churn_reason_code,feed_version --> |
| `your-gcp-project.acme_analytics.events` | `renewal_reminder_sent` was never implemented server-side — email tool logs only. Do not expect the event in BQ until ACMEPLT-88 lands. **Source:** BIL-006, 2026-07-30. <!-- ctx: id=renewal_reminder_not_instrumented entity=event category=instrumentation_gap cols=event_name --> |
| `your-gcp-project.acme_analytics.signups` | `plan_tier` on signup is **requested** tier; paid tier lives on `subscriptions.plan_tier` after pay flow completes. Join signup → subscription on `user_id` for conversion dashboards. **Source:** CHK-003, 2026-08-19. <!-- ctx: id=signup_plan_vs_subscription_plan entity=signup category=entity_rule cols=plan_tier,user_id --> |

---

## Feed cutovers & temporal discontinuities

| Date | Change | Effect |
|---|---|---|
| 2026-09-01 | Funnel step names consolidated (`plan_review` + `wallet_entry` → `combined_step`) | Step-funnel queries must map legacy names before this date |
| 2026-09-25 | Churn feed v3 (`feed_version = 3`) | `churn_reason_code` NULL until backfill completes; see LIF-007 |

---

## When to add an entry

Add only non-obvious findings: silent nulls, double-fire events, attribution windows, unit traps. Skip routine column descriptions covered in `config/schemas/acme_*.yml`.
