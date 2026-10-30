#!/usr/bin/env python3
"""
Six Eyes Backlog Board — local Flask web app for browsing the backlog.
Single-user, read-only (except /refresh), localhost-only binding.
"""

import functools
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

import markdown
from flask import Flask, abort, redirect, render_template, request

# Setup paths
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import dashboard_helpers

# Constants
DB_PATH = REPO_ROOT / "metadata" / "sixeyes.db"
BACKLOG_DIR = REPO_ROOT / "data" / "backlog"
PORT = int(os.environ.get("BACKLOG_BOARD_PORT", "5151"))

TERMINAL_STATUSES = {"backburner", "done"}
STATUS_ORDER = ["active", "monitoring", "waiting", "backburner", "done"]
SORT_COLUMNS = {
    "score": "priority_score",
    "module": "module",
    "status": "status",
    "stale": "stale_weeks",
    "esc": "escalation_level",
    "id": "id",
    "title": "title"
}

# Flask app
app = Flask(__name__, template_folder="templates", static_folder="static")


def get_db_connection():
    """Open a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def make_qs(current, **overrides):
    """Build a query string, preserving current filters and applying overrides."""
    merged = {**current, **overrides}
    merged = {k: v for k, v in merged.items() if v not in (None, "")}
    return "?" + urlencode(merged) if merged else "/"


def row_to_dict(row):
    """Convert sqlite3.Row to dict."""
    return dict(row) if row else None


@app.route("/")
def table_view():
    """Table view of backlog items."""
    # Parse and validate query params
    sort = request.args.get("sort", "score")
    if sort not in SORT_COLUMNS:
        sort = "score"

    dir = request.args.get("dir", "desc")
    if dir not in ("asc", "desc"):
        dir = "desc"

    module = request.args.get("module", "all")
    status = request.args.get("status", "__active__")
    esc_only = request.args.get("esc_only")

    # Build current filter dict for query string builder
    current_filters = {
        "sort": sort if sort != "score" else None,
        "dir": dir if dir != "desc" else None,
        "module": module if module != "all" else None,
        "status": status if status != "__active__" else None,
        "esc_only": esc_only if esc_only else None,
    }

    # Build SQL query
    conn = get_db_connection()
    cursor = conn.cursor()

    # Base query
    query = "SELECT * FROM items WHERE 1=1"
    params = []

    # Module filter
    if module != "all":
        query += " AND module = ?"
        params.append(module)

    # Status filter
    if status == "__active__":
        # Exclude terminal statuses
        placeholders = ",".join("?" * len(TERMINAL_STATUSES))
        query += f" AND status NOT IN ({placeholders})"
        params.extend(TERMINAL_STATUSES)
    elif status != "all":
        query += " AND status = ?"
        params.append(status)

    # Escalation filter
    if esc_only == "1":
        query += " AND escalation_level >= 1"

    # Sorting
    order_col = SORT_COLUMNS[sort]
    query += f" ORDER BY {order_col} {dir.upper()}"

    cursor.execute(query, params)
    items = cursor.fetchall()

    # Compute mention_gap and convert to dicts
    items_list = []
    for item in items:
        item_dict = row_to_dict(item)
        item_dict["mention_gap"] = item_dict["mention_count"] - item_dict["progress_count"]
        items_list.append(item_dict)

    # Get distinct statuses for filter dropdown
    cursor.execute("SELECT DISTINCT status FROM items ORDER BY status")
    distinct_statuses = [row[0] for row in cursor.fetchall()]

    conn.close()

    # Prepare module and status options
    module_options = dashboard_helpers.MODULE_LABEL
    status_options = distinct_statuses

    # Create qs closure
    qs = functools.partial(make_qs, current_filters)

    return render_template(
        "table.html",
        items=items_list,
        module_options=module_options,
        status_options=status_options,
        current_module=module,
        current_status=status,
        current_sort=sort,
        current_dir=dir,
        esc_only_checked=(esc_only == "1"),
        qs=qs,
        priority_dot=dashboard_helpers.priority_dot,
        status_label=dashboard_helpers.status_label,
        agent_step=dashboard_helpers.agent_step_state,
    )


@app.route("/kanban")
def kanban_view():
    """Kanban view of backlog items."""
    module = request.args.get("module", "all")

    # Build current filter dict
    current_filters = {
        "module": module if module != "all" else None,
    }

    # Fetch all items for this module (no status filter)
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM items WHERE 1=1"
    params = []

    if module != "all":
        query += " AND module = ?"
        params.append(module)

    cursor.execute(query, params)
    items = cursor.fetchall()

    # Get distinct statuses for filter dropdown
    cursor.execute("SELECT DISTINCT status FROM items ORDER BY status")
    distinct_statuses = [row[0] for row in cursor.fetchall()]

    conn.close()

    # Group items by status
    items_by_status = {}
    for item in items:
        status = item["status"]
        if status not in items_by_status:
            items_by_status[status] = []
        items_by_status[status].append(row_to_dict(item))

    # Order columns: STATUS_ORDER first, then any remaining
    ordered_columns = []
    for status in STATUS_ORDER:
        if status in items_by_status:
            ordered_columns.append((status, items_by_status[status]))

    # Append any statuses not in STATUS_ORDER
    remaining_statuses = sorted(set(items_by_status.keys()) - set(STATUS_ORDER))
    for status in remaining_statuses:
        ordered_columns.append((status, items_by_status[status]))

    # Sort items within each column by priority_score DESC
    for status, item_list in ordered_columns:
        item_list.sort(key=lambda x: x["priority_score"], reverse=True)

    module_options = dashboard_helpers.MODULE_LABEL
    qs = functools.partial(make_qs, current_filters)

    return render_template(
        "kanban.html",
        columns=ordered_columns,
        module_options=module_options,
        current_module=module,
        qs=qs,
        priority_dot=dashboard_helpers.priority_dot,
        agent_step=dashboard_helpers.agent_step_state,
    )


@app.route("/item/<item_id>")
def detail_view(item_id):
    """Detail view of a single item."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    item = cursor.fetchone()

    if not item:
        conn.close()
        abort(404)

    item_dict = row_to_dict(item)

    # Try to find markdown file
    markdown_file = None
    matching_files = list(BACKLOG_DIR.glob(f"{item_id}-*.md"))
    if matching_files:
        markdown_file = matching_files[0]

    rendered_html = ""
    if markdown_file:
        body = markdown_file.read_text()

        # Split frontmatter
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", body, re.DOTALL)
        if m:
            body_text = m.group(2)
        else:
            body_text = body

        # Build set of known IDs for wikilink conversion
        cursor.execute("SELECT id FROM items")
        known_ids = {row[0] for row in cursor.fetchall()}

        # Convert wikilinks to markdown links
        def replace_wikilink(match):
            inner = match.group(1)
            # Check if it's an ID format (e.g., ONB-013) and exists in DB
            if re.fullmatch(r'[A-Z]{2,4}-\d+', inner) and inner in known_ids:
                return f"[{inner}](/item/{inner})"
            else:
                # Plain text, brackets stripped
                return inner

        body_text = re.sub(r'\[\[([^\]]+)\]\]', replace_wikilink, body_text)

        # Render markdown to HTML
        rendered_html = markdown.markdown(body_text, extensions=['fenced_code', 'tables'])

    # Parse cross_modules
    cross_modules_list = []
    if item_dict.get("cross_modules"):
        try:
            import json
            cross_modules_list = json.loads(item_dict["cross_modules"])
        except (json.JSONDecodeError, TypeError):
            pass

    conn.close()

    return render_template(
        "detail.html",
        item=item_dict,
        rendered_html=rendered_html,
        cross_modules=cross_modules_list,
        module_options=dashboard_helpers.MODULE_LABEL,
        module_label=dashboard_helpers.MODULE_LABEL.get(item_dict["module"], item_dict["module"]),
        priority_dot=dashboard_helpers.priority_dot,
        status_label=dashboard_helpers.status_label,
        agent_step=dashboard_helpers.agent_step_state,
        markdown_found=(markdown_file is not None),
    )


@app.route("/refresh", methods=["POST"])
def refresh():
    """Refresh the database by running sync-metadata.py."""
    next_path = request.form.get("next", "/")

    # Validate next_path: must start with "/" and not start with "//"
    if not next_path.startswith("/") or next_path.startswith("//"):
        next_path = "/"

    # Run the sync script
    try:
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sync-metadata.py")],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=60,
            shell=False
        )
    except subprocess.TimeoutExpired:
        # If sync times out, still redirect (user can retry)
        pass
    except Exception:
        # If sync fails, still redirect
        pass

    return redirect(next_path, code=302)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)
