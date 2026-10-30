---
aliases: ["LIF-007"]
id: LIF-007
title: "churn_reason_code NULL after lifecycle feed v3"
module: lifecycle
cross_modules: ["platform"]
status: active
business_impact: 4
time_sensitivity: 5
data_readiness: 4
agent_next_step: "Profile NULL churn_reason_code rate by feed_version in acme_analytics_staging.stg_lifecycle_churn_feed"
agent_step_type: "investigate"
agent_step_check: null
agent_step_as_of: "2026-10-14"
created: 2026-09-01
last_touched: 2026-10-14
last_progress: 2026-10-14
mention_count: 4
progress_count: 3
stale_weeks: 0
blocked_reason: null
escalation_level: 0
priority_score: 87.00
---
## Context
Feed cutover 2026-09-25; backfill ticket ACMELIF-77 open.

## Links
- [[PLT-009]]
