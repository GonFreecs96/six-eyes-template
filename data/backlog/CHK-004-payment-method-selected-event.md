---
aliases: ["CHK-004"]
id: CHK-004
title: "payment_method_selected not emitted for wallet pay"
module: checkout
cross_modules: []
status: waiting
business_impact: 3
time_sensitivity: 3
data_readiness: 2
agent_next_step: "Check ACMECHK-142 status: if Done, validate event volume in acme_analytics.events"
agent_step_type: "check"
agent_step_check: null
agent_step_as_of: "2026-09-22"
created: 2026-09-05
last_touched: 2026-09-22
last_progress: 2026-09-10
mention_count: 3
progress_count: 1
stale_weeks: 2
blocked_reason: "Blocked on ACMECHK-142 wallet instrumentation"
escalation_level: 1
priority_score: 55.00
---
## Context
Wallet pay path skips legacy instrumentation hook.
