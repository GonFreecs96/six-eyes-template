---
aliases: ["ONB-002"]
id: ONB-002
title: "Signup funnel drops anonymous_id after account link without mapping table"
module: onboarding
cross_modules: ["checkout"]
status: monitoring
business_impact: 3
time_sensitivity: 2
data_readiness: 4
agent_next_step: null
agent_step_type: null
agent_step_check: null
agent_step_as_of: "2026-09-15"
created: 2026-08-20
last_touched: 2026-09-15
last_progress: 2026-09-15
mention_count: 2
progress_count: 2
stale_weeks: 2
blocked_reason: null
escalation_level: 1
priority_score: 58.00
---
## Context
Marketing uses anonymous_id pre-signup; product analytics pivots to user_id. Bridge is inferential.

## Notes
Monitoring until identity graph ships (ACMEPLT-44).
