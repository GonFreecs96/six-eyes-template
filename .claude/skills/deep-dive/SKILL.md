---
name: deep-dive
description: Focused investigation on a specific backlog item. Pulls all related context and produces a structured findings doc.
allowed-tools:
  - Read
  - Write
  - Bash(python3:*)
  - mcp__atlassian__searchJiraIssuesUsingJql
  - mcp__atlassian__getJiraIssue
  - mcp__atlassian__searchConfluenceUsingCql
  - mcp__atlassian__getConfluencePage
  - mcp__atlassian__createConfluencePage
  - mcp__atlassian__updateConfluencePage
  - mcp__atlassian__getConfluencePageDescendants
  - mcp__slack__slack_read_channel
  - mcp__slack__slack_read_thread
  - mcp__slack__slack_search_public_and_private
---

# Skill: Deep Dive

## Purpose
Produce a focused, structured investigation on a single backlog item. Output lives as a child page under the relevant module's Deep Dives folder in Confluence.

## Invocation
```
/deep-dive [item-id]
```
Example: `/deep-dive ONB-001` or `/deep-dive CHK-003`

## Step 0 — Load backlog item
Read `data/backlog/[item-id].md`. Extract: title, module, status, links (Jira tickets), tags, any existing notes.

If the item mentions warehouse verification, schema, `acme_analytics`, or specific columns: load `config/context/entity-rules.yaml`, `integration-payload-traps.yaml`, and `feed-cutovers.yaml` first, then grep targeted sections in `data/bq-knowledge.md`. Before raw SQL, use `metric-catalog` and `scripts/lib/bq_client.py` (dry-run, read-only).

If the file doesn't exist, tell the operator and stop.

## Step 1 — Pull Jira context

**Context economy:** Steps 1–3 pull large Jira/Confluence/Slack blobs that would
otherwise sit in the session context for the whole investigation. Delegate each
pull batch to a subagent (Agent tool): give it the ticket keys / queries and have it
return only a compact extraction (status history highlights, decision-relevant
comments, links) — not the raw responses. Pull directly only when a single small
fetch is needed.

For each Jira ticket in the item's `links` frontmatter:
- `getJiraIssue` for full details (description, comments, status history)
- `searchJiraIssuesUsingJql` for related tickets: `issueLinks` or same epic, last 90 days

## Step 2 — Pull Confluence context
Search for existing RFCs, specs, or design docs related to the item title keywords:
```
searchConfluenceUsingCql: title ~ "[keyword]" AND space = "ACME"
```
Fetch the top 2-3 most relevant pages.

## Step 3 — Pull Slack context
Use `slack_search_public_and_private` with 2-3 keywords from the item title across:
- The relevant module channel (e.g. `#acme-onboarding`, `#acme-checkout`, `#acme-billing`, `#acme-lifecycle`, `#acme-data`)
- `#acme-analytics` for cross-cutting warehouse discussion

For any high-signal results, expand the thread with `slack_read_thread`.

## Step 4 — Check prior pulse check mentions
Read pulse check files from `data/pulse-checks/` (flat; filenames `YYYY-WXX-pulse.md`, last 8 weeks). Search for mentions of the item ID or title keywords. Collect relevant excerpts.

## Step 5 — Check meeting notes
Read `data/meetings/*.md` files from the last 30 days. Search for mentions of item title keywords. Collect relevant excerpts.

## Step 6 — Draft the deep dive page

Structure:
```markdown
# Deep Dive — [Item Title]
**Category:** [Onboarding | Checkout | Billing | Lifecycle | Platform]
**Backlog Item:** [item-id]
**Status:** [current status]
**Date:** [today]

## Summary
2-3 sentences. What is this about and why does it matter analytically?

## Findings
What we know. Key facts from Jira, Confluence, Slack, and meetings.
Keep this tight — bullets preferred. No raw quotes.

## Open Questions
What we still don't know. What's blocking resolution?
- [ ] Question 1
- [ ] Question 2

## Recommended Next Steps
Ordered list of specific actions with owners where known.

---

## Appendix

### Jira Tickets
[ticket key + summary + status for each referenced ticket]

### Confluence References
[page title + link for each referenced page]

### Slack Signals
[channel, date, brief summary of relevant thread — no full quotes]

### Pulse Check History
[date + one-line excerpt for each pulse check mention]
```

If the investigation surfaced any non-obvious BQ facts (per the trigger patterns in `data/bq-knowledge.md` → "When to add an entry"), propose corresponding `bq-knowledge.md` entries alongside the deep-dive draft. Each proposed entry: one-or-two-sentence claim, source backlog ID + date. Findings that belong in the appendix (raw SQL, full query results) stay in the appendix and do not get logged.

Present the draft (deep-dive page + any `bq-knowledge.md` entries) to the operator for review. Do not publish to Confluence without explicit confirmation.

## Step 7 — On confirmation, publish
Determine the correct Deep Dives parent page from `config/confluence-registry.yaml`
(module → folder mapping). If no folder exists for Platform-only work, place under the
most relevant product module or the operator's draft space in Acme Confluence.

Check for existing page with same title using `getConfluencePageDescendants` on the folder.
- If none exists: `createConfluencePage` with `parentId` = folder page ID
- If exists: `updateConfluencePage` with `versionMessage: "[date] — updated via deep dive skill"`

## Step 8 — Update backlog item
After successful publish, update the backlog item's frontmatter:
- Set `last_touched` to today's date
- Append the Confluence page URL to `links`

Present the frontmatter update for confirmation before writing.
