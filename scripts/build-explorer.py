#!/usr/bin/env python3
"""
build-explorer.py - regenerate docs/six-eyes-explorer.html from the live repo.

The interactive explorer is a single self-contained HTML file (theme tokens,
Tabler icon webfont + Chart.js from CDN, a sendPrompt shim that copies a
question to the clipboard). This script is the source of truth for it: it
carries the HTML/CSS/JS template and injects a fresh snapshot of the repo:

  - backlog items        <- data/backlog/*.md frontmatter (excl. _completed-*)
  - cross-module signals <- data/signals/cross-module-registry.json
  - BigQuery reference   <- curated acme_analytics.* tables, column counts from config/schemas/*.yml
  - counts + dates       <- pulse-checks / deep-dives / meetings / skills, workflow-state

Run:
  unset GOOGLE_APPLICATION_CREDENTIALS
  .venv/bin/python scripts/build-explorer.py

Static curation (skills catalog, category PMs, BQ table list, gotchas) lives in
this file because it is not cleanly machine-readable elsewhere; the live data is
everything dated. Re-run after a weekly scan to refresh the snapshot.
"""

import glob
import json
import re
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
    HAVE_YAML = True
except Exception:
    HAVE_YAML = False

from dashboard_helpers import normalize_step_field, parse_as_of

REPO = Path(__file__).parent.parent
BACKLOG = REPO / "data" / "backlog"
SCHEMAS = REPO / "config" / "schemas"
REGISTRY = REPO / "data" / "signals" / "cross-module-registry.json"
STATE = REPO / "data" / "state" / "workflow-state.json"
LAST_RUN_MD = REPO / "data" / "state" / "last-run-summary.md"
OUT = REPO / "docs" / "six-eyes-explorer.html"

ITEM_KEYS = ["id", "title", "module", "cross_modules", "status", "business_impact",
             "time_sensitivity", "data_readiness", "mention_count", "progress_count",
             "stale_weeks", "escalation_level", "priority_score", "agent_next_step",
             "agent_step_type", "agent_step_check", "agent_step_as_of", "blocked_reason"]


def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    if HAVE_YAML:
        try:
            return yaml.safe_load(block)
        except Exception:
            pass
    d = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip().strip('"')
    return d


def squash(t, n):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def to_int(v, default=0):
    try:
        return int(round(float(v)))
    except Exception:
        return default


def load_items():
    items = []
    for f in sorted(BACKLOG.glob("*.md")):
        if f.name.startswith("_"):
            continue
        fm = parse_frontmatter(f.read_text())
        if not fm or not fm.get("id"):
            continue
        cm = fm.get("cross_modules") or []
        if isinstance(cm, str):
            cm = [c.strip() for c in cm.strip("[]").split(",") if c.strip()]
        br = fm.get("blocked_reason")
        ns = normalize_step_field(fm.get("agent_next_step"))
        nc = normalize_step_field(fm.get("agent_step_check"))
        nt = normalize_step_field(fm.get("agent_step_type"), lower=True)
        na, _ = parse_as_of(fm.get("agent_step_as_of"))
        items.append({
            "id": fm.get("id"),
            "t": fm.get("title", ""),
            "m": fm.get("module", ""),
            "cm": [c for c in cm if c],
            "s": fm.get("status", ""),
            "bi": to_int(fm.get("business_impact")),
            "ts": to_int(fm.get("time_sensitivity")),
            "dr": to_int(fm.get("data_readiness")),
            "mc": to_int(fm.get("mention_count")),
            "pc": to_int(fm.get("progress_count")),
            "sw": to_int(fm.get("stale_weeks")),
            "e": to_int(fm.get("escalation_level")),
            "sc": to_int(fm.get("priority_score")),
            "ns": squash(ns, 240) if ns else None,
            "nt": nt,
            "nc": squash(nc, 240) if nc else None,
            "na": na,
            "br": squash(br, 240) if br else None,
        })
    return items


def load_signals():
    if not REGISTRY.is_file():
        return [], ""
    reg = json.loads(REGISTRY.read_text())
    out = []
    for l in reg.get("links", []):
        st = l.get("status")
        if st == "archived":
            continue
        out.append({
            "a": l.get("id_a"),
            "b": l.get("id_b"),
            "type": l.get("type", ""),
            "conf": to_int(l.get("confidence")),
            "status": st if st in ("dormant", "stale") else None,
            "desc": squash(l.get("description", ""), 280),
            "last": l.get("last_confirmed", ""),
        })
    return out, reg.get("updated", "")


def schema_ncols(fname):
    p = SCHEMAS / fname
    if not p.exists() or not HAVE_YAML:
        return None
    try:
        d = yaml.safe_load(p.read_text())
        return len(d["models"][0].get("columns", []))
    except Exception:
        return None


def load_bq():
    tables = [
        {"name": "signups", "grain": "Account signup events",
         "use": "Trial starts and channel attribution.",
         "keys": ["signup_id", "user_id", "client_surface"],
         "schema_file": "acme_signups.yml"},
        {"name": "subscriptions", "grain": "Subscription lifecycle",
         "use": "Trial → paid → churn states.",
         "keys": ["subscription_id", "user_id", "plan_tier"],
         "schema_file": "acme_subscriptions.yml"},
        {"name": "invoices", "grain": "Billing invoices",
         "use": "MRR movements and failed payments.",
         "keys": ["invoice_id", "subscription_id"],
         "schema_file": "acme_invoices.yml"},
        {"name": "events", "grain": "Product analytics events",
         "use": "Funnel steps; JSON payloads vary by integration partner.",
         "keys": ["event_id", "user_id", "event_name"],
         "schema_file": "acme_events.yml"},
        {"name": "partner_referrals", "grain": "Referral partner rows",
         "use": "Partner-attributed signups.",
         "keys": ["referral_id", "partner_code"],
         "schema_file": "acme_partner_referrals.yml"},
    ]
    for t in tables:
        t["ncols"] = schema_ncols(t["schema_file"]) if t["schema_file"] else None
        del t["schema_file"]
    gotchas = [
        "Project <span class=\"mono\">your-gcp-project</span> · dataset <span class=\"mono\">acme_analytics</span>.",
        "Use <span class=\"mono\">scripts/lib/bq_client.py</span> — dry-run first, read-only SQL only.",
        "Event JSON paths differ by partner — check <span class=\"mono\">integration-payload-traps.yaml</span>.",
        "Trial conversion windows straddle feed cutovers — see <span class=\"mono\">feed-cutovers.yaml</span>.",
    ]
    return tables, gotchas


def fmt_day(d):
    return "{} {}".format(d.day, d.strftime("%b"))


def fmt_full(d):
    return "{} {} {}".format(d.day, d.strftime("%b"), d.year)


def load_meta(items):
    counts = {
        "items": len(items),
        "skills": len([p for p in (REPO / ".claude" / "skills").glob("*") if p.is_dir()]),
        "pulse": len(glob.glob(str(REPO / "data" / "pulse-checks" / "*.md"))),
        "dives": len(glob.glob(str(REPO / "data" / "deep-dives" / "*.md"))),
        "meet": len(glob.glob(str(REPO / "data" / "meetings" / "*.md"))),
    }
    active = None
    if LAST_RUN_MD.exists():
        m = re.search(r"Active items:\**\s*(\d+)", LAST_RUN_MD.read_text())
        if m:
            active = int(m.group(1))
    if active is None:
        live = {"active", "monitoring", "waiting"}
        active = sum(1 for i in items if i["s"] in live)
    counts["active"] = active

    last_run = ""
    if STATE.exists():
        try:
            lr = json.loads(STATE.read_text()).get("last_run", "")
            last_run = fmt_day(datetime.fromisoformat(lr.replace("Z", "+00:00")).date())
        except Exception:
            last_run = ""
    return counts, last_run


def js(obj):
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def build():
    items = load_items()
    signals, reg_updated = load_signals()
    bq_tables, gotchas = load_bq()
    counts, last_run = load_meta(items)
    today = date.today()
    thresholds = json.loads((REPO / "config" / "scoring-weights.json").read_text())["staleness_thresholds"]

    repl = {
        "__FLAG_WEEKS__": str(thresholds["flag_weeks"]),
        "__ESCALATE_WEEKS__": str(thresholds["escalate_weeks"]),
        "__MENTION_THRESHOLD__": str(thresholds["stale_mention_threshold"]),
        "__ITEMS_JSON__": js(items),
        "__SIGNALS_JSON__": js(signals),
        "__BQ_JSON__": js(bq_tables),
        "__GOTCHAS_JSON__": js(gotchas),
        "__SNAPSHOT__": fmt_full(today),
        "__LASTRUN__": last_run or "n/a",
        "__N_ITEMS__": str(counts["items"]),
        "__N_ACTIVE__": str(counts["active"]),
        "__N_SKILLS__": str(counts["skills"]),
        "__N_PULSE__": str(counts["pulse"]),
        "__N_DIVES__": str(counts["dives"]),
        "__N_MEET__": str(counts["meet"]),
        "__SIG_UPDATED__": reg_updated or "n/a",
    }
    out = TEMPLATE
    for k, v in repl.items():
        out = out.replace(k, v)
    OUT.write_text(out, encoding="utf-8")
    print("Wrote {} ({:,} bytes)".format(OUT.relative_to(REPO), len(out)))
    print("  {} backlog items | {} active | {} cross-module signals".format(
        counts["items"], counts["active"], len(signals)))
    print("  snapshot {} | last run {}".format(fmt_full(today), last_run or "n/a"))


TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Six Eyes - interactive explorer</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.47.0/tabler-icons.min.css">
<style>
:root{
  --color-background-primary:#ffffff;
  --color-background-secondary:#f4f3ee;
  --color-background-tertiary:#faf9f5;
  --color-background-info:#E6F1FB;
  --color-background-danger:#FCEBEB;
  --color-background-success:#EAF3DE;
  --color-background-warning:#FAEEDA;
  --color-text-primary:#201f1d;
  --color-text-secondary:#5f5e5a;
  --color-text-tertiary:#8a8980;
  --color-text-info:#0C447C;
  --color-text-danger:#791F1F;
  --color-text-success:#27500A;
  --color-text-warning:#633806;
  --color-border-tertiary:rgba(0,0,0,0.12);
  --color-border-secondary:rgba(0,0,0,0.22);
  --color-border-primary:rgba(0,0,0,0.32);
  --color-border-info:#85B7EB;
  --font-sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --font-serif:Georgia,"Times New Roman",serif;
  --font-mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --border-radius-md:8px;
  --border-radius-lg:12px;
  --border-radius-xl:16px;
}
@media (prefers-color-scheme: dark){
  :root{
    --color-background-primary:#302f2d;
    --color-background-secondary:#262523;
    --color-background-tertiary:#1d1c1b;
    --color-background-info:#103251;
    --color-background-danger:#3a1a1a;
    --color-background-success:#1c2f10;
    --color-background-warning:#3a2910;
    --color-text-primary:#eceae2;
    --color-text-secondary:#b8b6ac;
    --color-text-tertiary:#8a8980;
    --color-text-info:#B5D4F4;
    --color-text-danger:#F09595;
    --color-text-success:#C0DD97;
    --color-text-warning:#FAC775;
    --color-border-tertiary:rgba(255,255,255,0.14);
    --color-border-secondary:rgba(255,255,255,0.26);
    --color-border-primary:rgba(255,255,255,0.36);
    --color-border-info:#185FA5;
  }
}
html,body{margin:0;padding:0}
body{background:var(--color-background-tertiary);color:var(--color-text-primary);font-family:var(--font-sans);line-height:1.6;-webkit-font-smoothing:antialiased}
.page{max-width:860px;margin:0 auto;padding:30px 24px 64px}
.mono{font-family:var(--font-mono)}
input[type=range]{accent-color:#378ADD;width:100%;height:20px}
select{font:inherit;font-size:13px;padding:6px 8px;border-radius:var(--border-radius-md);border:0.5px solid var(--color-border-secondary);background:var(--color-background-primary);color:var(--color-text-primary)}
button{font-family:inherit}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(20px);background:var(--color-text-primary);color:var(--color-background-primary);padding:11px 18px;border-radius:var(--border-radius-md);font-size:13px;max-width:540px;opacity:0;transition:opacity .25s,transform .25s;pointer-events:none;z-index:50;box-shadow:0 6px 24px rgba(0,0,0,.18)}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
.se-wrap{padding:.5rem 0;font-size:16px;line-height:1.6}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}
.se-h{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.se-title{font-size:22px;font-weight:500;margin:0;display:flex;align-items:center;gap:9px}
.se-tag{font-size:14px;color:var(--color-text-secondary);margin:5px 0 0;max-width:470px}
.se-stamp{font-size:12px;color:var(--color-text-tertiary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:7px 11px;white-space:nowrap;line-height:1.4}
.se-nav{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px;border-bottom:0.5px solid var(--color-border-tertiary);padding-bottom:12px}
.se-nav button{font:inherit;font-size:13px;padding:7px 12px;border-radius:var(--border-radius-md);border:0.5px solid var(--color-border-tertiary);background:transparent;color:var(--color-text-secondary);cursor:pointer;display:flex;align-items:center;gap:6px}
.se-nav button:hover{background:var(--color-background-secondary)}
.se-nav button.on{background:var(--color-background-secondary);color:var(--color-text-primary);border-color:var(--color-border-secondary)}
.se-sec h3{font-size:16px;font-weight:500;margin:1.5rem 0 .7rem}
.se-lead{color:var(--color-text-secondary);font-size:15px;margin:.2rem 0 1.1rem;line-height:1.65}
.grid{display:grid;gap:12px}
.metric{background:var(--color-background-secondary);border-radius:var(--border-radius-md);padding:13px 14px}
.metric .n{font-size:24px;font-weight:500}
.metric .l{font-size:12.5px;color:var(--color-text-secondary);margin-top:1px;line-height:1.35}
.card{background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-lg);padding:14px 16px}
.card h4{font-size:14.5px;font-weight:500;margin:0 0 5px;display:flex;align-items:center;gap:8px}
.card p{margin:0;font-size:13px;color:var(--color-text-secondary);line-height:1.55}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
.chip{font-size:12px;padding:4px 10px;border-radius:var(--border-radius-md);background:var(--color-background-secondary);color:var(--color-text-secondary);border:0.5px solid var(--color-border-tertiary);cursor:pointer}
.chip:hover{border-color:var(--color-border-secondary)}
.chip.on{background:var(--color-background-info);color:var(--color-text-info);border-color:var(--color-border-info)}
.pill{font-size:11px;padding:2px 8px;border-radius:var(--border-radius-md);white-space:nowrap}
.bar{height:6px;border-radius:4px;background:var(--color-background-secondary);overflow:hidden}
.bar > i{display:block;height:100%;background:#378ADD;border-radius:4px}
.flow{display:flex;align-items:stretch;flex-wrap:wrap;gap:6px}
.flow .step{flex:1 1 88px;min-width:88px;background:var(--color-background-secondary);border-radius:var(--border-radius-md);padding:9px 8px;font-size:12px;text-align:center;border:0.5px solid var(--color-border-tertiary)}
.flow .arr{display:flex;align-items:center;color:var(--color-text-tertiary)}
.band{background:var(--color-background-secondary);border-radius:var(--border-radius-md);padding:12px 15px}
.band h4{margin:0 0 2px;font-size:14.5px;font-weight:500;display:flex;align-items:center;gap:8px}
.band p{margin:0;font-size:12.5px;color:var(--color-text-secondary)}
.chev{display:flex;justify-content:center;color:var(--color-text-tertiary);padding:3px 0}
.skill{border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-lg);padding:12px 14px;background:var(--color-background-primary);cursor:pointer}
.skill:hover{border-color:var(--color-border-secondary)}
.skill .nm{font-size:14px;font-weight:500;display:flex;align-items:center;gap:8px;justify-content:space-between}
.skill .ds{font-size:12.5px;color:var(--color-text-secondary);margin:6px 0 9px;line-height:1.5}
.skill .mt{display:flex;flex-wrap:wrap;gap:5px;align-items:center}
.tag{font-size:11px;padding:2px 8px;border-radius:var(--border-radius-md);background:var(--color-background-secondary);color:var(--color-text-secondary);font-family:var(--font-mono)}
.item{border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:10px 12px;margin-bottom:8px;cursor:pointer}
.item:hover{border-color:var(--color-border-secondary)}
.item .top{display:flex;align-items:center;gap:9px}
.item .idc{font-family:var(--font-mono);font-size:12px;color:var(--color-text-secondary);flex:none}
.item .tt{font-size:13.5px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .det{display:none;margin-top:10px;padding-top:10px;border-top:0.5px solid var(--color-border-tertiary);font-size:13px;color:var(--color-text-secondary);line-height:1.55}
.item.open .det{display:block}
.item.open .tt{white-space:normal}
.btn{font:inherit;font-size:12px;padding:6px 11px;border-radius:var(--border-radius-md);border:0.5px solid var(--color-border-secondary);background:transparent;color:var(--color-text-primary);cursor:pointer;display:inline-flex;align-items:center;gap:5px}
.btn:hover{background:var(--color-background-secondary)}
.muted{color:var(--color-text-tertiary);font-size:12px}
.sl{display:flex;align-items:center;gap:12px;margin:0 0 10px}
.sl label{font-size:13px;color:var(--color-text-secondary);min-width:118px}
.sl input{flex:1}
.sl .o{font-size:14px;font-weight:500;min-width:18px;text-align:right}
.callout{background:var(--color-background-info);border-radius:var(--border-radius-md);padding:11px 14px;font-size:12.5px;color:var(--color-text-info);line-height:1.55}
ul li::marker{color:var(--color-text-tertiary)}
</style>
</head>
<body>
<div class="page">
<div class="se-wrap">
<h2 class="sr-only">Interactive explorer for Six Eyes: an overview, the three-layer architecture, the workflow skill catalog, the five-category model with priority scoring, the cross-module signal graph, the BigQuery table reference, and a live snapshot of the __N_ITEMS__-item backlog as of __SNAPSHOT__.</h2>
<div class="se-h">
  <div>
    <p class="se-title"><i class="ti ti-eye" aria-hidden="true"></i>Six Eyes - interactive explorer</p>
    <p class="se-tag">A Claude-first analytics intelligence template for Acme (subscription app): composable skills, read-only warehouse checks, and a self-scoring backlog.</p>
  </div>
  <div class="se-stamp">Live snapshot<br>__SNAPSHOT__ &middot; last run __LASTRUN__</div>
</div>
<div class="se-nav">
  <button class="on" data-nav="overview" onclick="show('overview')"><i class="ti ti-eye" aria-hidden="true"></i>Overview</button>
  <button data-nav="arch" onclick="show('arch')"><i class="ti ti-stack-2" aria-hidden="true"></i>Architecture</button>
  <button data-nav="skills" onclick="show('skills')"><i class="ti ti-list-check" aria-hidden="true"></i>Skills &amp; workflow</button>
  <button data-nav="cats" onclick="show('cats')"><i class="ti ti-category" aria-hidden="true"></i>Categories &amp; scoring</button>
  <button data-nav="cross" onclick="show('cross')"><i class="ti ti-affiliate" aria-hidden="true"></i>Cross-module</button>
  <button data-nav="bq" onclick="show('bq')"><i class="ti ti-database" aria-hidden="true"></i>BigQuery</button>
  <button data-nav="backlog" onclick="show('backlog')"><i class="ti ti-chart-bar" aria-hidden="true"></i>Backlog (live)</button>
</div>

<section class="se-sec" id="sec-overview">
  <p class="se-lead">Think of it as a tireless analyst's assistant. Every week it reads the Jira tickets and meeting notes across five categories, notices what shipped and what's quietly at risk, scores it, and tells you what to look at today. It never acts on its own - it drafts, you approve.</p>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(135px,1fr))">
    <div class="metric"><div class="n">__N_ITEMS__</div><div class="l">tracked backlog items</div></div>
    <div class="metric"><div class="n">__N_ACTIVE__</div><div class="l">active at last run</div></div>
    <div class="metric"><div class="n">__N_SKILLS__</div><div class="l">workflow skills</div></div>
    <div class="metric"><div class="n">__N_PULSE__</div><div class="l">weekly pulse scans</div></div>
    <div class="metric"><div class="n">__N_DIVES__</div><div class="l">deep-dive reports</div></div>
    <div class="metric"><div class="n">__N_MEET__</div><div class="l">meetings ingested</div></div>
  </div>
  <h3>What it can do</h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(205px,1fr))">
    <div class="card"><h4><i class="ti ti-search" aria-hidden="true"></i>Detect</h4><p>Weekly Jira scan for shipped features, in-flight work, and analytics risks across all five categories.</p></div>
    <div class="card"><h4><i class="ti ti-star" aria-hidden="true"></i>Remember &amp; prioritize</h4><p>Scores every item 0-100 and escalates anything that stalls or gets discussed without progress.</p></div>
    <div class="card"><h4><i class="ti ti-refresh" aria-hidden="true"></i>Correlate</h4><p>Catches signals that span two or more categories so nothing falls in the gap between them.</p></div>
    <div class="card"><h4><i class="ti ti-microscope" aria-hidden="true"></i>Investigate</h4><p>Runs focused BigQuery investigations - human-led (deep-dive) or agent-run (agent-work).</p></div>
    <div class="card"><h4><i class="ti ti-calendar" aria-hidden="true"></i>Brief</h4><p>Answers "what needs my attention right now?" daily and synthesizes a weekly briefing.</p></div>
    <div class="card"><h4><i class="ti ti-send" aria-hidden="true"></i>Hand off</h4><p>Turns a finished investigation into drafted Slack/Jira/email and a stakeholder-ready Confluence page - you send.</p></div>
  </div>
  <h3>Why it matters</h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
    <div class="card"><h4><i class="ti ti-shield-check" aria-hidden="true"></i>Catches risks pre-production</h4><p>Flags instrumentation gaps and silent metric breakage - like proto enum bumps - before they reach prod.</p></div>
    <div class="card"><h4><i class="ti ti-bell" aria-hidden="true"></i>Nothing rots silently</h4><p>An item discussed 3+ times without progress on a high score escalates automatically: a decision bottleneck, not slow work.</p></div>
    <div class="card"><h4><i class="ti ti-cpu" aria-hidden="true"></i>Token-efficient by design</h4><p>Replaced a 160K-token monolith with composable skills, each in its own fresh ~15-30K context.</p></div>
    <div class="card"><h4><i class="ti ti-refresh" aria-hidden="true"></i>Compounds weekly</h4><p>Every run builds on prior intelligence, stored as Git-versioned markdown + YAML.</p></div>
    <div class="card"><h4><i class="ti ti-check" aria-hidden="true"></i>Drafts, you approve</h4><p>Never publishes, mutates the backlog, or sends a message without a draft and explicit approval.</p></div>
  </div>
  <p class="muted" style="margin-top:14px">Tip: every card and item in this explorer is clickable - it copies a question you can paste into Claude Code to go deeper on that piece.</p>
</section>

<section class="se-sec" id="sec-arch" style="display:none">
  <p class="se-lead">Local-first and Claude-first: every artifact is a file under Git. A rebuildable SQLite index powers scoring, staleness, and cross-module correlation. Confluence is a publishing destination, never a source of truth.</p>
  <h3>Three-layer system</h3>
  <div class="band"><h4><span class="dot" style="background:#888780"></span>Trigger layer</h4><p>Manual invocation in Cursor &middot; weekly run script &middot; optional cron / launchd</p></div>
  <div class="chev"><i class="ti ti-chevron-down" aria-hidden="true"></i></div>
  <div class="band"><h4><span class="dot" style="background:#7F77DD"></span>Intelligence layer</h4><p>Claude Code skills &middot; scoped MCP servers (Atlassian &middot; Slack &middot; Filesystem &middot; Granola)</p></div>
  <div class="chev"><i class="ti ti-chevron-down" aria-hidden="true"></i></div>
  <div class="band"><h4><span class="dot" style="background:#1D9E75"></span>Data layer</h4><p>Local markdown + YAML frontmatter &middot; SQLite metadata index &middot; Git versioning</p></div>
  <h3>Core principles</h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
    <div class="card"><h4><i class="ti ti-folder" aria-hidden="true"></i>Local-first</h4><p>Markdown + YAML is human-readable in Cursor and machine-parseable by Claude. Git gives versioning and diffs.</p></div>
    <div class="card"><h4><i class="ti ti-list-check" aria-hidden="true"></i>Composable skills</h4><p>Each skill runs in a fresh context and loads only its own MCP servers - no session crosses the degradation threshold.</p></div>
    <div class="card"><h4><i class="ti ti-check" aria-hidden="true"></i>Human-in-the-loop</h4><p>Claude drafts; the human approves. Externally-visible actions are never auto-invoked.</p></div>
    <div class="card"><h4><i class="ti ti-file" aria-hidden="true"></i>Compressed-state handoff</h4><p>Skills talk via files, not shared context - each reads a ~500-token state summary plus only what it needs.</p></div>
  </div>
  <h3>Backlog item lifecycle</h3>
  <div class="flow">
    <div class="step">watching</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step">active</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step">resolved</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step">backburner</div>
  </div>
  <p class="muted" style="margin-top:7px">active sub-states: not_started &middot; scoping &middot; in_progress &middot; monitoring &middot; blocked. Resolved items move to a per-category <span class="tag">_completed-{module}.md</span> archive.</p>
  <h3>Data layer detail</h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
    <div class="card"><h4><i class="ti ti-file" aria-hidden="true"></i>Markdown + YAML</h4><p>One file per item. Frontmatter = machine-queryable metadata; body = problem, signals, progress log.</p></div>
    <div class="card"><h4><i class="ti ti-database" aria-hidden="true"></i>SQLite index</h4><p>Tables: items &middot; pulse_mentions &middot; score_history &middot; cross_module_links &middot; items_fts. Rebuildable from frontmatter + pulse checks; git-ignored.</p></div>
    <div class="card"><h4><i class="ti ti-refresh" aria-hidden="true"></i>Git versioning</h4><p>Frontmatter is the source of truth. Delete and re-sync the DB anytime - nothing is lost.</p></div>
  </div>
</section>

<section class="se-sec" id="sec-skills" style="display:none">
  <p class="se-lead">The weekly workflow is decomposed into discrete skills. The orchestrated run chains four of them in staging mode, then presents one consolidated review gate before promoting anything.</p>
  <h3>Orchestrated weekly run</h3>
  <div class="flow">
    <div class="step">pulse-scan</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step">opportunity-scan</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step">staleness-check</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step">weekly-brief</div><div class="arr"><i class="ti ti-arrow-right" aria-hidden="true"></i></div>
    <div class="step" style="background:var(--color-background-info);color:var(--color-text-info);border-color:var(--color-border-info)">one review gate &rarr; promote</div>
  </div>
  <p class="muted" style="margin-top:7px">meeting-ingest runs separately so its budget cap can't truncate the chain. Staging mode writes proposals to <span class="tag">data/staging/</span> first; nothing reaches its final home until you approve.</p>
  <h3>Skills catalog</h3>
  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">
    <span class="chip on" data-gf="all">All</span>
    <span class="chip" data-gf="weekly">Weekly pipeline</span>
    <span class="chip" data-gf="investigate">Investigate &amp; hand off</span>
    <span class="chip" data-gf="agent">Agent-workable</span>
    <span class="chip" data-gf="orchestrate">Orchestrate &amp; publish</span>
    <span class="chip" data-gf="design">Planning &amp; design</span>
  </div>
  <div class="grid" id="skills" style="grid-template-columns:repeat(auto-fit,minmax(225px,1fr))"></div>
  <h3>Daily commands</h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">
    <div class="card" style="cursor:pointer" onclick="sendPrompt('What does the /today command surface in Six Eyes and how does it decide what is urgent?')"><h4><i class="ti ti-clock" aria-hidden="true"></i>/today</h4><p>The most urgent items right now, with action recommendations and contact names.</p></div>
    <div class="card" style="cursor:pointer" onclick="sendPrompt('What does the /status command in Six Eyes show?')"><h4><i class="ti ti-eye" aria-hidden="true"></i>/status</h4><p>Snapshot of current state: last run dates, item counts, pending escalations.</p></div>
  </div>
</section>

<section class="se-sec" id="sec-cats" style="display:none">
  <p class="se-lead">Five modules — Onboarding, Checkout, Billing, Lifecycle, and Platform analytics. Each maps to a Jira project key and backlog prefix.</p>
  <h3>Categories</h3>
  <div class="grid" id="cats" style="grid-template-columns:repeat(auto-fit,minmax(215px,1fr))"></div>
  <div class="callout" style="margin-top:12px"><i class="ti ti-info-circle" aria-hidden="true"></i> Jira projects <span class="mono">ACMEONB</span>, <span class="mono">ACMECHK</span>, <span class="mono">ACMEBIL</span>, <span class="mono">ACMELIF</span>, <span class="mono">ACMEPLT</span> (live mode). Backlog IDs use <span class="mono">ONB-</span> / <span class="mono">CHK-</span> / <span class="mono">BIL-</span> / <span class="mono">LIF-</span> / <span class="mono">PLT-</span> prefixes.</div>
  <h3>Priority score calculator</h3>
  <div class="card">
    <p style="margin-bottom:14px" class="mono" >score = (business &times; 0.40 + time &times; 0.35 + readiness &times; 0.25) &times; 20</p>
    <div class="sl"><label>Business impact</label><input type="range" min="1" max="5" step="1" value="4" id="bi" oninput="calc()"><span class="o" id="biO">4</span></div>
    <div class="sl"><label>Time sensitivity</label><input type="range" min="1" max="5" step="1" value="4" id="ts" oninput="calc()"><span class="o" id="tsO">4</span></div>
    <div class="sl"><label>Data readiness</label><input type="range" min="1" max="5" step="1" value="3" id="dr" oninput="calc()"><span class="o" id="drO">3</span></div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-top:8px"><span style="font-size:28px;font-weight:500" id="calcScore">75</span><span class="muted" id="calcBand"></span></div>
    <div class="bar" style="margin-top:8px"><i id="calcBar" style="width:75%"></i></div>
  </div>
  <h3>Staleness &amp; escalation ladder</h3>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(205px,1fr))">
    <div class="card"><h4><span class="pill" style="background:var(--color-background-warning);color:var(--color-text-warning)">level 1</span>__FLAG_WEEKS__ weeks no progress</h4><p>Yellow indicator on the dashboard - flagged for a look.</p></div>
    <div class="card"><h4><span class="pill" style="background:var(--color-background-danger);color:var(--color-text-danger)">level 2</span>__ESCALATE_WEEKS__ weeks no progress</h4><p>Weekly brief explicitly recommends descope / reassign / escalate.</p></div>
    <div class="card"><h4><span class="pill" style="background:var(--color-background-danger);color:var(--color-text-danger)">immediate</span>__MENTION_THRESHOLD__+ mentions, no progress</h4><p>Escalates regardless of weeks (level 2 if score &gt; 60) - a decision bottleneck, not slow progress.</p></div>
  </div>
</section>

<section class="se-sec" id="sec-cross" style="display:none">
  <p class="se-lead">Three mechanisms stop signals splitting between categories: multi-module tagging, a shared signal registry, and a wiki-link backlink graph. The graph sizes each category by how many items touch it and links categories that share items. Click a node to filter the signals below; click a signal to dig in.</p>
  <div class="card"><div id="graph"></div></div>
  <div style="display:flex;flex-wrap:wrap;gap:6px;margin:1.1rem 0 .8rem;align-items:center">
    <span class="chip on" id="sigAll" onclick="sigFilter=null;document.getElementById('sigAll').classList.add('on');renderSignals();">All signals</span>
    <span class="muted" id="sigCount"></span>
    <span style="flex:1"></span>
    <span class="muted">registry updated __SIG_UPDATED__</span>
  </div>
  <div class="grid" id="signals" style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr))"></div>
</section>

<section class="se-sec" id="sec-bq" style="display:none">
  <p class="se-lead">The curated <span class="mono">acme_analytics</span> warehouse Six Eyes investigates against. Column schemas live in <span class="mono">config/schemas/</span>; badges show documented column counts.</p>
  <div class="callout" style="margin-bottom:14px"><i class="ti ti-database" aria-hidden="true"></i> Project <span class="mono">your-gcp-project</span> &middot; dataset <span class="mono">acme_analytics</span> &middot; use <span class="mono">scripts/lib/bq_client.py</span> (read-only, dry-run first).</div>
  <h3>Core tables</h3>
  <div class="grid" id="bqTables" style="grid-template-columns:repeat(auto-fit,minmax(250px,1fr))"></div>
  <h3>Join keys &amp; gotchas</h3>
  <ul id="bqGotchas" style="font-size:13px;color:var(--color-text-secondary);line-height:1.65;padding-left:20px;margin:0"></ul>
  <p class="muted" style="margin-top:12px">For non-obvious findings, silent-null cases, and feed cutover dates, read <span class="tag">data/bq-knowledge.md</span> before framing queries.</p>
</section>

<section class="se-sec" id="sec-backlog" style="display:none">
  <p class="se-lead">The actual backlog as of __SNAPSHOT__ - __N_ITEMS__ tracked items. Filter by category, toggle escalated-only, and re-sort. Click any item to see its dimensions, blockers, and dig in.</p>
  <div class="grid" id="blMetrics" style="grid-template-columns:repeat(auto-fit,minmax(135px,1fr));margin-bottom:6px"></div>
  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));margin:1rem 0">
    <div class="card">
      <h4 style="margin-bottom:10px">By category</h4>
      <div id="modLegend" style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px;font-size:12px;color:var(--color-text-secondary)"></div>
      <div style="position:relative;height:170px"><canvas id="modChart" role="img" aria-label="Doughnut chart of backlog items by category"></canvas></div>
    </div>
    <div class="card">
      <h4 style="margin-bottom:10px">By priority score</h4>
      <div style="position:relative;height:200px"><canvas id="priChart" role="img" aria-label="Bar chart of backlog items grouped by priority score band"></canvas></div>
    </div>
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:.4rem 0 1rem">
    <span class="chip on" data-mod="all">All</span>
    <span class="chip" data-mod="onboarding">Onboarding</span>
    <span class="chip" data-mod="checkout">Checkout</span>
    <span class="chip" data-mod="billing">Billing</span>
    <span class="chip" data-mod="lifecycle">Lifecycle</span>
    <span class="chip" data-mod="platform">Platform</span>
    <span class="chip" id="escToggle" style="margin-left:4px"><i class="ti ti-bell" aria-hidden="true" style="font-size:13px;vertical-align:-1px"></i> Escalated only</span>
    <span style="flex:1;min-width:10px"></span>
    <label class="muted" style="display:flex;align-items:center;gap:6px">Sort
      <select id="sortSel" style="width:auto;display:inline-block">
        <option value="sc">Priority score</option>
        <option value="comp">Priority &times; escalation</option>
        <option value="sw">Staleness (weeks)</option>
        <option value="gap">Mention gap</option>
      </select>
    </label>
  </div>
  <div class="muted" id="count" style="margin-bottom:8px"></div>
  <div id="items"></div>
</section>
</div>
<p class="muted" style="text-align:center;margin-top:30px">Generated __SNAPSHOT__ by <span class="mono">scripts/build-explorer.py</span> &middot; static snapshot of the Six Eyes repo</p>
</div>
<div class="toast" id="seToast"></div>
<script>
var toastT;
function showToast(msg){var el=document.getElementById('seToast');el.textContent=msg;el.classList.add('on');clearTimeout(toastT);toastT=setTimeout(function(){el.classList.remove('on');},2600);}
window.sendPrompt=function(t){try{if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(t);}catch(e){}showToast('Copied - paste into Claude Code: "'+(t.length>72?t.slice(0,72)+'…':t)+'"');};
window.openLink=function(u){window.open(u,'_blank');};
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const ITEMS=__ITEMS_JSON__;
const SIGNALS=__SIGNALS_JSON__;
const BQ=__BQ_JSON__;
const GOTCHAS=__GOTCHAS_JSON__;
const MOD={"onboarding":{label:"Onboarding",c:"#7F77DD"},"checkout":{label:"Checkout",c:"#378ADD"},"billing":{label:"Billing",c:"#1D9E75"},"lifecycle":{label:"Lifecycle",c:"#BA7517"},"platform":{label:"Platform",c:"#D4537E"}};
const CATS=[
{label:"Onboarding",type:"product module",pre:"ONB",jira:"ACMEONB",slack:"#acme-onboarding",pm:"Elena Voss",c:"#7F77DD"},
{label:"Checkout",type:"product module",pre:"CHK",jira:"ACMECHK",slack:"#acme-checkout",pm:"Marco Chen",c:"#378ADD"},
{label:"Billing",type:"product module",pre:"BIL",jira:"ACMEBIL",slack:"#acme-billing",pm:"Priya Nair",c:"#1D9E75"},
{label:"Lifecycle",type:"product module",pre:"LIF",jira:"ACMELIF",slack:"#acme-lifecycle",pm:"Jordan Blake",c:"#BA7517"},
{label:"Platform",type:"analytics",pre:"PLT",jira:"ACMEPLT",slack:"#acme-data",pm:"Sam Ortiz",c:"#D4537E"}
];
const SKILLS=[
{n:"six-eyes-run",g:"orchestrate",mcp:["shells claude -p"],ph:"Orchestrator",d:"One-command weekly run: stages the whole pipeline, then one consolidated review gate + promote.",gr:"never publishes or dispatches"},
{n:"pulse-scan",g:"weekly",mcp:["Atlassian"],ph:"Phase 1",d:"Weekly Jira scan; creates/updates backlog items and writes the pulse check."},
{n:"meeting-ingest",g:"weekly",mcp:["Granola cache"],ph:"Phase 3",d:"Scans recent Granola transcripts for analytics signals and matches them to backlog items."},
{n:"opportunity-scan",g:"weekly",mcp:["Filesystem"],ph:"Phase 3",d:"Cross-module tag co-occurrence; updates the cross-module signal registry."},
{n:"staleness-check",g:"weekly",mcp:["Filesystem"],ph:"Phase 2",d:"Computes priority scores, flags stale items, generates the priority dashboard."},
{n:"weekly-brief",g:"weekly",mcp:["Filesystem"],ph:"Phase 2",d:"Synthesizes every signal source into the weekly briefing."},
{n:"deep-dive",g:"investigate",mcp:["Atlassian","Slack"],ph:"Phase 4",d:"Human-led focused investigation on a single item, producing a structured findings doc."},
{n:"agent-triage",g:"agent",mcp:["Filesystem"],ph:"Phase 5",d:"Classifies each item by how much of its investigation an agent can do; writes the agent queue.",gr:"triage only"},
{n:"agent-work",g:"agent",mcp:["bq_client.py"],ph:"Phase 5",d:"Runs a triaged item's investigation end-to-end via read-only BigQuery; drafts findings + progress.",gr:"never dispatches"},
{n:"close-loop",g:"investigate",mcp:["Atlassian/Slack (read)"],ph:"Phase 4",d:"Turns a completed investigation into a review-ready handoff bundle of drafted messages + in-repo changes.",gr:"drafts only - never sends"},
{n:"retro",g:"output",mcp:["Filesystem"],ph:"On-demand",d:"Inward retrospective - proposes review-gated changes to Six Eyes itself across five buckets.",gr:"drafts only"},
{n:"design-interview",g:"design",mcp:["Filesystem"],ph:"Planning",d:"Structured interview for ideation, scoping, and planning a new project or feature - walks the design tree one decision at a time, exploring the codebase instead of asking when the answer is discoverable."},
{n:"schema-watch",g:"investigate",mcp:["GitHub"],ph:"Shelved",d:"GitHub PR schema-change detection - would close the biggest remaining signal gap. Shelved.",sh:true}
];
const $=id=>document.getElementById(id);
const SECS=["overview","arch","skills","cats","cross","bq","backlog"];
function show(sec){SECS.forEach(s=>{$("sec-"+s).style.display=(s===sec)?"block":"none";const b=document.querySelector('[data-nav="'+s+'"]');if(b)b.classList.toggle("on",s===sec);});if(sec==="backlog")initCharts();}
function modInfo(m){return MOD[m]||{label:m,c:"#888780"};}
function hx(s){return String(s).split("&").join("&amp;").split('"').join("&quot;").split("<").join("&lt;");}
function escStyle(e){return e>=2?"background:var(--color-background-danger);color:var(--color-text-danger)":e===1?"background:var(--color-background-warning);color:var(--color-text-warning)":"background:var(--color-background-secondary);color:var(--color-text-tertiary)";}
const state={mod:"all",escOnly:false,sort:"sc"};
function renderItems(){
  let arr=ITEMS.slice();
  if(state.mod!=="all")arr=arr.filter(i=>i.m===state.mod);
  if(state.escOnly)arr=arr.filter(i=>i.e>=1);
  const so=state.sort;
  arr.sort((a,b)=>so==="sw"?b.sw-a.sw:so==="gap"?(b.mc-b.pc)-(a.mc-a.pc):so==="comp"?(b.sc*(1+b.e*0.5))-(a.sc*(1+a.e*0.5)):b.sc-a.sc);
  $("items").innerHTML=arr.map(i=>{
    const m=modInfo(i.m),gap=i.mc-i.pc;
    return '<div class="item" onclick="this.classList.toggle(\'open\')">'+
      '<div class="top"><span class="dot" style="background:'+m.c+'" title="'+m.label+'"></span>'+
      '<span class="idc">'+i.id+'</span><span class="tt">'+i.t+'</span>'+
      '<span class="pill" style="'+escStyle(i.e)+'">esc '+i.e+'</span>'+
      '<span style="font-size:13px;font-weight:500;min-width:24px;text-align:right">'+Math.round(i.sc)+'</span></div>'+
      '<div class="bar" style="margin-top:8px"><i style="width:'+Math.round(i.sc)+'%"></i></div>'+
      '<div class="det"><div style="margin-bottom:8px"><span style="color:var(--color-text-primary);font-weight:500">'+i.t+'</span></div>'+
      '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px">'+
      '<span class="tag">'+m.label+'</span><span class="tag">'+i.s+'</span>'+
      ((i.cm&&i.cm.length)?'<span class="tag">cross: '+i.cm.join(", ")+'</span>':'')+
      '<span class="tag">BI '+i.bi+' &middot; TS '+i.ts+' &middot; DR '+i.dr+'</span>'+
      '<span class="tag">mentions '+i.mc+' / progress '+i.pc+' (gap '+gap+')</span>'+
      '<span class="tag">stale '+i.sw+'w</span><span class="tag">agent: '+(i.nt==="investigate"?"🔍 investigate":i.nt==="check"?"⏱ check":"-")+'</span></div>'+
      (i.ns?'<div style="margin-bottom:9px;font-size:13px" title="'+hx(i.ns)+'">next: '+hx(i.ns.length>100?i.ns.slice(0,99)+"…":i.ns)+'</div>':'')+
      (i.br?'<div style="margin-bottom:9px">'+i.br+'</div>':'')+
      '<button class="btn" onclick="event.stopPropagation();sendPrompt(\'Walk me through '+i.id+' in Six Eyes: current status, why it is scored the way it is, and what the next action is.\')">Dig into '+i.id+' <i class="ti ti-arrow-right" aria-hidden="true"></i></button></div></div>';
  }).join("");
  $("count").textContent=arr.length+" of "+ITEMS.length+" items";
}
function renderBlMetrics(){
  const esc=ITEMS.filter(i=>i.e>=1).length;
  const hp=ITEMS.filter(i=>i.sc>60).length;
  const aw=ITEMS.filter(i=>i.ns).length;
  const cards=[[ITEMS.length,"tracked items"],[esc,"escalated (level 1+)"],[hp,"high priority (&gt;60)"],[aw,"has agent step"]];
  $("blMetrics").innerHTML=cards.map(c=>'<div class="metric"><div class="n">'+c[0]+'</div><div class="l">'+c[1]+'</div></div>').join("");
}
function renderSkills(){
  $("skills").innerHTML=SKILLS.map(s=>{
    const grp=(s.g==="orchestrate"||s.g==="output")?"orchestrate":s.g;
    return '<div class="skill" data-g="'+grp+'" onclick="sendPrompt(\'Explain the '+s.n+' skill in Six Eyes: what it does, when I would run it, and what it reads and writes.\')">'+
      '<div class="nm"><span style="display:flex;align-items:center;gap:7px">'+(s.sh?'<i class="ti ti-player-pause" aria-hidden="true"></i>':'')+'/'+s.n+'</span><span class="tag">'+s.ph+'</span></div>'+
      '<div class="ds">'+s.d+'</div>'+
      '<div class="mt">'+s.mcp.map(m=>'<span class="tag">'+m+'</span>').join("")+(s.gr?'<span class="pill" style="background:var(--color-background-warning);color:var(--color-text-warning)">'+s.gr+'</span>':'')+'</div></div>';
  }).join("");
  var ac=document.querySelector('[data-gf="all"]');if(ac)ac.textContent="All ("+SKILLS.length+")";
}
function renderCats(){
  $("cats").innerHTML=CATS.map(c=>'<div class="card"><h4><span class="dot" style="background:'+c.c+'"></span>'+c.label+'</h4>'+
    '<p style="margin-bottom:8px">'+c.type+' &middot; prefix <span class="mono">'+c.pre+'</span></p>'+
    '<div style="font-size:12px;color:var(--color-text-secondary);line-height:1.7"><div><i class="ti ti-ticket" aria-hidden="true" style="font-size:13px;width:16px"></i>'+c.jira+'</div>'+
    '<div><i class="ti ti-message" aria-hidden="true" style="font-size:13px;width:16px"></i>'+c.slack+'</div>'+
    '<div><i class="ti ti-user" aria-hidden="true" style="font-size:13px;width:16px"></i>'+c.pm+'</div></div></div>').join("");
}
function calc(){
  const bi=+$("bi").value,ts=+$("ts").value,dr=+$("dr").value;
  $("biO").textContent=bi;$("tsO").textContent=ts;$("drO").textContent=dr;
  const sc=Math.round((bi*0.4+ts*0.35+dr*0.25)*20);
  $("calcScore").textContent=sc;$("calcBar").style.width=sc+"%";
  $("calcBand").textContent=sc>60?"surfaces on the dashboard (>60)":sc>=40?"mid priority":"low priority";
}
function renderGraph(){
  const cats=["onboarding","checkout","billing","lifecycle","platform"];
  const touch={};cats.forEach(c=>touch[c]=0);const edge={};
  function norm(i){const set=new Set([i.m]);(i.cm||[]).forEach(x=>{if(x)set.add(x);});return Array.from(set).filter(c=>cats.indexOf(c)>=0);}
  ITEMS.forEach(i=>{const set=norm(i);set.forEach(c=>touch[c]++);for(let a=0;a<set.length;a++)for(let b=a+1;b<set.length;b++){const k=[set[a],set[b]].sort().join("|");edge[k]=(edge[k]||0)+1;}});
  const cx=340,cy=178,R=122,pos={};
  cats.forEach((c,k)=>{const ang=(-90+k*72)*Math.PI/180;pos[c]={x:Math.round(cx+R*Math.cos(ang)),y:Math.round(cy+R*Math.sin(ang))};});
  let maxT=1;cats.forEach(c=>{if(touch[c]>maxT)maxT=touch[c];});
  let svg='<svg width="100%" viewBox="0 0 680 372" role="img" aria-label="Cross-module co-occurrence graph: five categories sized by item count, linked where items span both.">';
  Object.keys(edge).forEach(k=>{const p=k.split("|"),a=pos[p[0]],b=pos[p[1]],w=Math.min(7,1.2+edge[k]*1.3);svg+='<line x1="'+a.x+'" y1="'+a.y+'" x2="'+b.x+'" y2="'+b.y+'" style="stroke:var(--color-text-tertiary);stroke-width:'+w.toFixed(1)+'px;stroke-linecap:round;opacity:.4"/>';});
  cats.forEach(c=>{const p=pos[c],r=Math.round(16+12*(touch[c]/maxT)),above=p.y<cy,ly=above?p.y-r-9:p.y+r+17;
    svg+='<g style="cursor:pointer" onclick="filterSignals(\''+c+'\')">'+
    '<circle cx="'+p.x+'" cy="'+p.y+'" r="'+r+'" fill="'+MOD[c].c+'"/>'+
    '<text x="'+p.x+'" y="'+(p.y+4)+'" text-anchor="middle" font-size="13" style="fill:#fff;font-weight:500">'+touch[c]+'</text>'+
    '<text x="'+p.x+'" y="'+ly+'" text-anchor="middle" font-size="12" style="fill:var(--color-text-secondary)">'+MOD[c].label+'</text></g>';});
  svg+='</svg>';
  $("graph").innerHTML=svg;
}
let sigFilter=null;
function filterSignals(cat){sigFilter=(sigFilter===cat)?null:cat;$("sigAll").classList.toggle("on",!sigFilter);renderSignals();}
function renderSignals(){
  const id2m={};ITEMS.forEach(i=>id2m[i.id]=i.m);
  function res(x){return id2m[x]||x;}
  let arr=SIGNALS.filter(s=>{if(!sigFilter)return true;return res(s.a)===sigFilter||res(s.b)===sigFilter;});
  arr.sort((a,b)=>(a.status?1:0)-(b.status?1:0)||b.conf-a.conf);
  $("signals").innerHTML=arr.map(s=>{
    let dots="";for(let i=0;i<5;i++){dots+='<span style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:3px;'+(i<s.conf?"background:var(--color-text-secondary)":"border:0.5px solid var(--color-border-secondary)")+'"></span>';}
    const stat=s.status?'<span class="pill" style="background:var(--color-background-secondary);color:var(--color-text-tertiary)">'+s.status+'</span>':'<span class="pill" style="background:var(--color-background-success);color:var(--color-text-success)">active</span>';
    return '<div class="card" style="cursor:pointer" onclick="sendPrompt(\'Explain the cross-module link between '+s.a+' and '+s.b+' in Six Eyes: why they are coupled and what to watch.\')">'+
      '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px"><span style="font-weight:500;font-size:13.5px">'+s.a+' &harr; '+s.b+'</span><span class="muted">'+s.type+'</span></div>'+
      '<div style="display:flex;align-items:center;gap:8px;margin:7px 0">'+dots+stat+'</div>'+
      '<p style="font-size:12.5px;line-height:1.5">'+s.desc+'</p>'+
      '<div class="muted" style="margin-top:7px">last confirmed '+s.last+'</div></div>';
  }).join("");
  $("sigCount").textContent=arr.length+" signals"+(sigFilter?" &middot; "+(MOD[sigFilter]?MOD[sigFilter].label:sigFilter):"");
}
function renderBQ(){
  $("bqTables").innerHTML=BQ.map(t=>'<div class="card"><h4><i class="ti ti-table" aria-hidden="true"></i><span class="mono" style="font-size:13px">'+t.name+'</span></h4>'+
    '<p style="margin-bottom:8px">'+t.use+'</p>'+
    '<div class="mt" style="margin-bottom:8px"><span class="pill" style="background:var(--color-background-secondary);color:var(--color-text-secondary)">'+t.grain+'</span>'+(t.ncols?'<span class="pill" style="background:var(--color-background-success);color:var(--color-text-success)">'+t.ncols+' cols documented</span>':'<span class="pill" style="background:var(--color-background-secondary);color:var(--color-text-tertiary)">schema not in repo</span>')+'</div>'+
    '<div style="font-size:12px;color:var(--color-text-secondary)">keys&nbsp; '+t.keys.map(k=>'<span class="tag" style="margin:2px 2px 0 0;display:inline-block">'+k+'</span>').join("")+'</div></div>').join("");
  $("bqGotchas").innerHTML=GOTCHAS.map(g=>'<li style="margin-bottom:8px">'+g+'</li>').join("");
}
let charted=false;
function initCharts(){
  if(charted||typeof Chart==="undefined")return;charted=true;
  const dark=matchMedia("(prefers-color-scheme: dark)").matches;
  const tick=dark?"#c2c0b6":"#3d3d3a",grid=dark?"rgba(255,255,255,.08)":"rgba(0,0,0,.08)";
  const order=["onboarding","checkout","billing","lifecycle","platform"];
  const counts=order.map(m=>ITEMS.filter(i=>i.m===m).length);
  $("modLegend").innerHTML=order.map((m,i)=>'<span style="display:flex;align-items:center;gap:5px"><span style="width:10px;height:10px;border-radius:2px;background:'+MOD[m].c+'"></span>'+MOD[m].label+' '+counts[i]+'</span>').join("");
  new Chart($("modChart"),{type:"doughnut",data:{labels:order.map(m=>MOD[m].label),datasets:[{data:counts,backgroundColor:order.map(m=>MOD[m].c),borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:"58%",plugins:{legend:{display:false}}}});
  const bins=[0,0,0,0];
  ITEMS.forEach(i=>{if(i.sc<40)bins[0]++;else if(i.sc<60)bins[1]++;else if(i.sc<80)bins[2]++;else bins[3]++;});
  new Chart($("priChart"),{type:"bar",data:{labels:["<40","40-59","60-79","80+"],datasets:[{data:bins,backgroundColor:"#378ADD",borderWidth:0,borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:tick},grid:{display:false}},y:{ticks:{color:tick,precision:0},grid:{color:grid}}}}});
}
document.querySelectorAll("[data-mod]").forEach(c=>c.addEventListener("click",()=>{state.mod=c.dataset.mod;document.querySelectorAll("[data-mod]").forEach(x=>x.classList.toggle("on",x===c));renderItems();}));
$("escToggle").addEventListener("click",function(){state.escOnly=!state.escOnly;this.classList.toggle("on",state.escOnly);renderItems();});
$("sortSel").addEventListener("change",function(){state.sort=this.value;renderItems();});
document.querySelectorAll("[data-gf]").forEach(c=>c.addEventListener("click",()=>{const g=c.dataset.gf;document.querySelectorAll("[data-gf]").forEach(x=>x.classList.toggle("on",x===c));document.querySelectorAll("#skills .skill").forEach(card=>{card.style.display=(g==="all"||card.dataset.g===g)?"":"none";});}));
renderSkills();renderCats();renderBlMetrics();renderItems();renderGraph();renderSignals();renderBQ();calc();show("overview");
</script>
</body>
</html>
'''


if __name__ == "__main__":
    build()
