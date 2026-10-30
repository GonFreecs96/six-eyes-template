---
aliases: ["BIL-005"]
id: BIL-005
title: "Upgrade invoices missing proration line_items after billing deploy"
module: billing
cross_modules: ["lifecycle"]
status: active
business_impact: 5
time_sensitivity: 4
data_readiness: 3
agent_next_step: "Quantify share of upgrade invoices without line_type=proration since 2026-09-10"
agent_step_type: "investigate"
agent_step_check: "Finance confirmed totals reconcile \u2014 line-level gap only"
agent_step_as_of: "2026-10-12"
created: 2026-08-01
last_touched: 2026-10-12
last_progress: 2026-10-12
mention_count: 6
progress_count: 4
stale_weeks: 0
blocked_reason: null
escalation_level: 0
priority_score: 83.00
---
## Context
Revenue correct at header level; SKU-level reporting undercounts mid-cycle upgrades.
