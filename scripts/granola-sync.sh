#!/bin/bash
# scripts/granola-sync.sh
# Copies recent Granola meetings to data/meetings/ as structured markdown.
set -euo pipefail

CACHE="$HOME/Library/Application Support/Granola/cache-v3.json"
OUTPUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/meetings"
DAYS_BACK=${1:-14}

if [ ! -f "$CACHE" ]; then
  echo "ERROR: Granola cache not found at $CACHE" >&2
  exit 1
fi

if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$CACHE" 2>/dev/null; then
  echo "ERROR: cache-v3.json is not valid JSON — format may have changed. Aborting." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

GRANOLA_OUTPUT_DIR="$OUTPUT_DIR" GRANOLA_DAYS_BACK="$DAYS_BACK" python3 << 'PYEOF'
import json, os, sys
from datetime import datetime, timezone, timedelta

cache_path = os.path.join(os.environ["HOME"], "Library/Application Support/Granola/cache-v3.json")
output_dir = os.path.abspath(os.environ["GRANOLA_OUTPUT_DIR"])
days_back = int(os.environ["GRANOLA_DAYS_BACK"])
cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

with open(cache_path) as f:
    raw = json.load(f)

# Path: root → cache (JSON string) → state → documents / documentPanels
inner = json.loads(raw["cache"])
state = inner.get("state", {})
documents = state.get("documents", {})
doc_panels = state.get("documentPanels", {})
meetings_meta = state.get("meetingsMetadata", {})

if not documents:
    print("No documents found in state.documents.")
    sys.exit(0)


# --- ProseMirror → Markdown rendering ---
# Granola stores AI-generated panel content as a ProseMirror doc tree under
# state.documentPanels[doc_id][panel_id].content. The schema in use is small:
# block: doc, paragraph, heading, bulletList, orderedList, listItem, codeBlock,
#        hardBreak
# inline: text (with marks: strong, em, code, link), hardBreak, mention

def render_marks(text, marks):
    if not marks:
        return text
    types = {m.get("type") for m in marks if isinstance(m, dict)}
    out = text
    if "code" in types:
        out = f"`{out}`"
    if "strong" in types:
        out = f"**{out}**"
    if "em" in types:
        out = f"*{out}*"
    for m in marks:
        if isinstance(m, dict) and m.get("type") == "link":
            href = (m.get("attrs") or {}).get("href")
            if href:
                out = f"[{out}]({href})"
    return out


def render_inline(nodes):
    if not nodes:
        return ""
    parts = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        t = n.get("type")
        if t == "text":
            parts.append(render_marks(n.get("text", ""), n.get("marks") or []))
        elif t == "hardBreak":
            parts.append("\n")
        elif t == "mention":
            parts.append((n.get("attrs") or {}).get("text") or "")
        elif t in ("paragraph", "heading"):
            parts.append(render_inline(n.get("content") or []))
    return "".join(parts)


def render_block(node, indent=0, list_marker=None):
    if not isinstance(node, dict):
        return ""
    t = node.get("type")
    children = node.get("content") or []
    pad = "  " * indent

    if t == "doc":
        return "\n\n".join(s for s in (render_block(c) for c in children) if s).strip() + "\n"
    if t == "heading":
        level = (node.get("attrs") or {}).get("level", 2)
        return f"{'#' * level} {render_inline(children)}"
    if t == "paragraph":
        body = render_inline(children)
        return f"{pad}{body}" if indent else body
    if t == "bulletList":
        return "\n".join(s for s in (render_block(c, indent, "-") for c in children) if s)
    if t == "orderedList":
        return "\n".join(
            s for s in (render_block(c, indent, f"{i}.") for i, c in enumerate(children, start=1)) if s
        )
    if t == "listItem":
        first = children[0] if children else None
        rest = children[1:]
        head = ""
        if isinstance(first, dict):
            if first.get("type") == "paragraph":
                head = render_inline(first.get("content") or [])
            else:
                head = render_block(first, indent + 1).lstrip()
        line = f"{pad}{list_marker or '-'} {head}"
        tail = [render_block(c, indent + 1) for c in rest if isinstance(c, dict)]
        tail = [t for t in tail if t]
        if tail:
            line += "\n" + "\n".join(tail)
        return line
    if t == "codeBlock":
        lang = (node.get("attrs") or {}).get("language") or ""
        body = render_inline(children)
        return f"```{lang}\n{body}\n```"
    if t == "hardBreak":
        return "\n"
    # Fallback — render children as inline
    return render_inline(children)


def panel_markdown(doc_id):
    panels = doc_panels.get(doc_id, {})
    if not panels:
        return ""
    panel_list = [p for p in panels.values() if isinstance(p, dict) and not p.get("deleted_at")]
    rendered = []
    for p in panel_list:
        content = p.get("content")
        if isinstance(content, dict):
            md = render_block(content).strip()
            if md:
                title = p.get("title") or p.get("template_slug") or "Notes"
                if len(panel_list) > 1:
                    rendered.append(f"### {title}\n\n{md}")
                else:
                    rendered.append(md)
    return "\n\n".join(rendered).strip()


# --- Participants extraction ---
# people is a dict: {creator: {...}, attendees: [...], conferencing: {...}}
# Pull display names; fall back to emails or to the google_calendar_event attendees.

def extract_participants(m, meta):
    people = m.get("people")
    names = []
    if isinstance(people, dict):
        creator = people.get("creator") or {}
        if isinstance(creator, dict):
            n = creator.get("name") or creator.get("email")
            if n and n not in names:
                names.append(n)
        for a in people.get("attendees") or []:
            if not isinstance(a, dict):
                continue
            n = (((a.get("details") or {}).get("person") or {}).get("name") or {}).get("fullName")
            if not n:
                n = a.get("name") or a.get("email")
            if n and n not in names:
                names.append(n)
    elif isinstance(people, list):
        for p in people:
            if isinstance(p, dict):
                n = p.get("name") or p.get("email")
                if n and n not in names:
                    names.append(n)
    if not names:
        gcal = m.get("google_calendar_event") or {}
        for a in gcal.get("attendees") or []:
            if isinstance(a, dict) and a.get("email") and a["email"] not in names:
                names.append(a["email"])
    if not names and isinstance(meta, dict):
        for a in (meta.get("participants") or meta.get("attendees") or []):
            if isinstance(a, dict):
                n = a.get("name") or a.get("email")
                if n and n not in names:
                    names.append(n)
    return ", ".join(names)


items = list(documents.values()) if isinstance(documents, dict) else documents
written = 0
skipped_old = 0
empty_panels = 0

for m in items:
    if not isinstance(m, dict):
        continue

    raw_date = m.get("created_at") or m.get("date") or m.get("updated_at") or ""
    if not raw_date:
        continue

    try:
        if isinstance(raw_date, (int, float)):
            meeting_dt = datetime.fromtimestamp(raw_date / 1000 if raw_date > 1e10 else raw_date, tz=timezone.utc)
        else:
            meeting_dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        continue

    if meeting_dt < cutoff:
        skipped_old += 1
        continue

    title = (m.get("title") or m.get("name") or "Untitled Meeting").strip()
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip().replace(" ", "-")[:60]
    filename = f"{meeting_dt.strftime('%Y-%m-%d')}-{safe_title}.md"
    filepath = os.path.join(output_dir, filename)

    doc_id = m.get("id") or ""
    notes = panel_markdown(doc_id) if doc_id else ""
    if not notes:
        # Legacy fallbacks (Granola previously stored content here)
        legacy = m.get("notes_markdown") or m.get("notes_plain") or m.get("overview") or ""
        if isinstance(legacy, str) and legacy.strip():
            notes = legacy
        else:
            empty_panels += 1

    meta = meetings_meta.get(doc_id, {}) if doc_id else {}
    participants_str = extract_participants(m, meta).replace('"', "'")
    safe_title_yaml = title.replace('"', "'")

    md = f"""---
title: "{safe_title_yaml}"
date: {meeting_dt.strftime('%Y-%m-%d')}
participants: "{participants_str}"
source: granola-cache
---

# {title}
**Date:** {meeting_dt.strftime('%Y-%m-%d')}
**Participants:** {participants_str or 'unknown'}

## Notes

{notes if notes else '_(no panel content found)_'}
"""

    with open(filepath, "w") as out:
        out.write(md)
    written += 1

empty_note = f", {empty_panels} with no panel content" if empty_panels else ""
print(f"granola-sync: wrote {written} meetings (skipped {skipped_old} older than {days_back} days{empty_note}) → {output_dir}")
PYEOF
