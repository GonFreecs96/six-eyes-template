# Sample inputs (offline mode)

When `config/runtime.yaml` sets `mode: offline`, skills read Jira and meeting fixtures from this directory instead of live MCP APIs.

## Layout

- `jira/{KEY}.json` — one file per ticket; fields match pulse-scan expectations.
- `meetings/YYYY-MM-DD-{slug}.md` — Granola-style exports with YAML frontmatter.

Point `sample_inputs_dir` in runtime config here (default).
