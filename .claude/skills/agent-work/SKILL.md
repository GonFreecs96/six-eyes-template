---
name: agent-work
description: Execute a triaged investigate step with read-only BigQuery and context rules.
---

# agent-work

Runs one backlog `agent_next_step` of type investigate/check.

## Preflight

1. Read item frontmatter and Notes.
2. Load `config/context/entity-rules.yaml`, `integration-payload-traps.yaml`, `feed-cutovers.yaml`.
3. `metric-catalog` if the step mentions a named KPI.

## Warehouse

- Config: `config/runtime.yaml` + `scripts/lib/bq_client.py`
- Dry-run SQL first; respect byte cap.
- Example tables: `your-gcp-project.acme_analytics.signups`, `events`, `subscriptions`

## Output

- Append draft findings to staged backlog Notes or a deep-dive stub under staging.
- Update `agent_step_as_of`; do not send outbound messages.
