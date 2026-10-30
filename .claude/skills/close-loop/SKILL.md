---
name: close-loop
description: Draft Slack/Jira/email handoffs; never send.
---

# close-loop

Package findings into **draft** outbound artifacts and in-repo Notes updates.

## Inputs

- Backlog item ID(s)
- Optional pulse/deep-dive paths

## Confluence

Use `config/confluence-registry.yaml` (placeholder) to pick destination page titles — SEED fills IDs.

## Outputs

- Draft Slack message (markdown)
- Draft Jira comment body
- Optional email draft
- Append dispatch checklist to item Notes (pending / sent-modified — human confirms)

## Guardrail

Never call Slack/Jira/Confluence write tools without explicit user approval per action.

Example Acme copy only — no real workspace URLs in commits.
