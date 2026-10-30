---
aliases: ["ONB-001"]
id: ONB-001
title: "trial_started fires twice on mobile SDK retry"
module: onboarding
cross_modules: ["platform"]
status: active
business_impact: 4
time_sensitivity: 4
data_readiness: 4
agent_next_step: "Dedupe trial_started counts in acme_analytics.events for iOS builds since 2026-09-01"
agent_step_type: "investigate"
agent_step_check: "Confirm SDK version filter with mobile team"
agent_step_as_of: "2026-10-03"
created: 2026-08-12
last_touched: 2026-10-10
last_progress: 2026-10-03
mention_count: 5
progress_count: 3
stale_weeks: 2
blocked_reason: null
escalation_level: 1
priority_score: 80.00
---
## Context
Mobile clients retry trial activation; warehouse shows ~3.2% duplicate trial_started within 60s.

## Links
- [ACMEONB-201](https://example.atlassian.net/browse/ACMEONB-201)

## Notes
**2026-10-03** — Deep dive W41 confirmed dedupe key; waiting on SDK fix ETA.
