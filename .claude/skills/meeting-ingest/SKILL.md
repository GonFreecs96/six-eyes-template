---
name: meeting-ingest
description: Granola-style meeting transcripts → backlog signals.
---

# meeting-ingest

## Mode

- **offline** — read `sample-inputs/meetings/*.md` (YAML frontmatter: title, date, attendees, source: granola-export)
- **live** — Granola MCP meeting list + transcripts

Also ingest committed seeds under `data/meetings/` when present.

## Behavior

Extract analytics/instrumentation risks, cross-module dependencies, and follow-ups. Propose backlog creates/updates with ONB/CHK/BIL/LIF/PLT module tags.

## Staging

Respect `SIXEYES_STAGING` paths under `data/staging/staged/data/`.
