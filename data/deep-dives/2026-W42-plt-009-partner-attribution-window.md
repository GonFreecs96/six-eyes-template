---
item: PLT-009
title: Zanybyte attribution window vs warehouse default
date: 2026-10-14
author: Riley Foster
module: platform
related_backlog_items: [PLT-009, ONB-002]
related_jira_keys: [ACMEPLT-90]
accuracy_tier: confirmed
---

# PLT-009 — Zanybyte attribution window

**Date:** 2026-10-14 · **Module:** platform (cross: onboarding)

## Question

How many Zanybyte podcast signups fall outside the default 7-day attribution window but inside the contract 14-day window?

## Method

```sql
SELECT
  partner_code,
  attribution_window_days,
  COUNT(*) AS clicks,
  COUNTIF(signup_id IS NOT NULL) AS attributed_signups
FROM `your-gcp-project.acme_analytics.partner_referrals`
WHERE partner_code LIKE 'zanybyte%'
  AND click_ts >= TIMESTAMP('2026-09-01')
GROUP BY 1, 2;
```

Join to `signups` on `signup_id` for trial-start rate (not shown).

## Findings (fictional)

- **62%** of podcast campaign clicks carry `attribution_window_days = 14`; remainder use default 7.
- Re-running weekly partner KPIs with a fixed 7-day window **understates** attributed signups by **~18%** for September podcast flight.
- Product analytics app still assumes 7 days — mismatch drives partner-facing report variance.

## Next steps

Parameterize `reports/acme_referral_partner/extract.sql` with `@window_days`. Align product default after partner ops sign-off (Casey Ng, casey.ng@example.com).
