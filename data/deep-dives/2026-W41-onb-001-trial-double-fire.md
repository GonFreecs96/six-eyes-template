---
item: ONB-001
title: trial_started duplicate rate on mobile
date: 2026-10-07
author: Elena Voss
module: onboarding
related_backlog_items: [ONB-001]
related_jira_keys: [ACMEONB-201]
accuracy_tier: exploratory
---

# ONB-001 — trial_started duplicate rate on mobile

**Date:** 2026-10-07 · **Module:** onboarding

## Question

What share of `trial_started` events are duplicates within 60 seconds, and does dedupe change trial-start KPIs materially?

## Method

```sql
-- Placeholder; point config/runtime.yaml at your project before running live.
SELECT
  user_id,
  COUNT(*) AS raw_events,
  COUNT(DISTINCT event_id) AS distinct_events
FROM `your-gcp-project.acme_analytics.events`
WHERE event_name = 'trial_started'
  AND event_ts >= TIMESTAMP('2026-09-01')
  AND properties.platform IN ('ios', 'android')
GROUP BY 1
HAVING raw_events > distinct_events;
```

## Findings (fictional)

- **3.2%** of mobile users with at least one trial_started show duplicate rows within 60s (iOS 3.8%, Android 2.1%).
- Dedupe on `event_id` reduces weekly trial-start count by **~1.1%** portfolio-wide — within PM acceptance band but worth noting in exec dashboards.
- Duplicates cluster on SDK versions `< 4.2.0`.

## Recommendation

Ship SDK 4.2.0 broadly; until then document dedupe in metric definitions. Link finding to bq-knowledge `trial_started_double_fire` rule.
