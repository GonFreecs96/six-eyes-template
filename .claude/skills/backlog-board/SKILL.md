---
name: backlog-board
description: Local-only Flask app providing table, kanban, and detail views over the Six Eyes backlog for the operator's daily triage. Read-only except for a Refresh button that re-runs `sync-metadata.py`. Personal daily-driver tool — not for stakeholders.
allowed-tools:
  - Bash
---

# Skill: Backlog Board

## Purpose

A simple, read-only local HTTP server (Flask) that renders the Six Eyes backlog in three interactive views — a flat table, a kanban board grouped by status, and a detail view for individual items. Built for the operator's daily triage workflow; never shared with stakeholders. External stakeholders use Confluence pages from `config/confluence-registry.yaml` when you choose to publish.

## Invocation

```
/backlog-board                 # Defaults to start
/backlog-board start           # Start the server
/backlog-board stop            # Stop the server
/backlog-board status          # Check if running
```

## Procedure

1. Parse the argument (first positional param). If missing, default to `start`. If unrecognized, show the usage message and stop.

2. Dispatch the subcommand by running `bash scripts/backlog-board.sh <subcommand>` in the repo root:
   - `start`: launches the Flask app in the background, stores its PID, and reports the URL.
   - `stop`: kills the process and removes the PID file.
   - `status`: checks if the process is still running and reports its status.

3. Relay the script's stdout output back to the operator verbatim (the URL for `start`, the status for `status`, the confirmation for `stop`).

## What this is NOT

- **Not a write/edit surface.** The backlog board is read-only; there is no inline editing, no drag-and-drop mutation, no item creation or status changes from the UI. The only state-changing action available is the **Refresh button** (on the table view), which re-runs `scripts/sync-metadata.py` to re-index the backlog files. Item edits, status changes, and metadata updates happen directly in the markdown backlog files, not through the board.
  
- **Not published anywhere.** The backlog board is the operator's local view only — unpolished, unscheduled, and separate from any Confluence dashboard you publish manually.

- **Not a scheduler or dispatcher.** The board does not send Slack messages, create Jira tickets, or update status downstream. It's a read-only view with a local refresh button.

## Technical details

- **Language:** Python Flask, running on the local machine (`127.0.0.1`).
- **Default port:** `5151` (configurable via the `BACKLOG_BOARD_PORT` environment variable).
- **App location:** `webapp/backlog_board/app.py` (not modified by this skill).
- **PID file:** `data/state/backlog-board.pid` (created on `start`, removed on `stop`).
- **Log file:** `data/state/backlog-board.log` (captures stdout/stderr from the Flask process).
- **Dependencies:** Installed from `requirements.txt` on first run if not already present.

## Startup behavior

When `start` is invoked:
1. The script checks if a process is already running (idempotent — if it's already up, report that and exit 0).
2. If not running, it verifies that `flask` and `markdown` are importable; if not, it runs `pip install -r requirements.txt`.
3. It launches the Flask app via `nohup` in the background, stores the new PID, waits one second, and reports the URL.

## Never

- Never edit, commit, or push any files inside `webapp/backlog_board/` from this skill.
- Never write or modify the backlog items as a side effect of running this skill (the Refresh button does that via `sync-metadata.py`, which is the Flask app's own responsibility, not this skill's).
- Never publish to Confluence or send to Slack/Jira/email.
