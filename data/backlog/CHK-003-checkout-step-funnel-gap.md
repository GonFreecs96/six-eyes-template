---
aliases: ["CHK-003"]
id: CHK-003
title: "funnel_step_viewed missing between plan_select and combined_step"
module: checkout
cross_modules: ["onboarding"]
status: active
business_impact: 4
time_sensitivity: 3
data_readiness: 3
agent_next_step: "Compare funnel_step_viewed sequence to server logs for web funnel v3.4"
agent_step_type: "investigate"
agent_step_check: "Segment by platform=web only"
agent_step_as_of: "2026-10-08"
created: 2026-08-28
last_touched: 2026-10-08
last_progress: 2026-10-08
mention_count: 4
progress_count: 2
stale_weeks: 1
blocked_reason: null
escalation_level: 0
priority_score: 68.00
---
## Context
Step rename cutover 2026-09-01 plus a missing client emit on promo entry.

## Links
- [[ONB-002]]
