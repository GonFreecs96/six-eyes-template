---
aliases: ["ONB-010"]
id: ONB-010
title: "No warehouse flag for verified email \u2014 proxy via signup completion step"
module: onboarding
cross_modules: ["billing"]
status: waiting
business_impact: 3
time_sensitivity: 2
data_readiness: 2
agent_next_step: "Check ACMEONB-310 for email_verified_at landing in signups table"
agent_step_type: "check"
agent_step_check: null
agent_step_as_of: "2026-10-01"
created: 2026-09-18
last_touched: 2026-10-01
last_progress: 2026-09-25
mention_count: 2
progress_count: 1
stale_weeks: 2
blocked_reason: "Waiting on identity service column user.email_verified_at"
escalation_level: 1
priority_score: 48.00
---
## Context
Trial-to-paid cohort analyses need verified-email slice.
