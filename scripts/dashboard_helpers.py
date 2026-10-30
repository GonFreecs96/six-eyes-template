"""
Reusable helper functions and constants for Six Eyes dashboard rendering.
Extracted from render-dashboard-html.py for shared use across dashboard tools.
"""

import html
import json
import re
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
MODULES_CONFIG_PATH = REPO_ROOT / "config" / "modules.json"


def load_module_labels():
    """category id -> display name, read from config/modules.json. Carries a frozen
    legacy 'app-checkout' label so pre-split items still render during migration."""
    labels = {"app-checkout": "App & Checkout"}
    try:
        cfg = json.loads(MODULES_CONFIG_PATH.read_text())
        for cat in cfg.get("categories", []):
            if cat.get("id") and cat.get("name"):
                labels[cat["id"]] = cat["name"]
    except (json.JSONDecodeError, OSError):
        pass
    return labels


MODULE_LABEL = load_module_labels()

NULL_TOKENS = {"", "none", "null", "~"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_step_field(value, lower: bool = False):
    """Shared normalizer for agent_step_* values.

    None, bool, list and dict -> None (YAML non-scalars are not valid step text).
    Otherwise str(value).strip(), and the null-like tokens '', 'none', 'null', '~'
    (case-insensitive) -> None. lower=True also lowercases (agent_step_type).
    """
    if value is None or isinstance(value, (bool, list, dict)):
        return None
    s = str(value).strip()
    if s.lower() in NULL_TOKENS:
        return None
    return s.lower() if lower else s


def is_bad_step_value(value) -> bool:
    """True for YAML values normalize_step_field discards (bool/list/dict)."""
    return isinstance(value, (bool, list, dict))


def parse_as_of(value):
    """Return (normalized_str_or_None, is_valid). Valid = YYYY-MM-DD and a real calendar date.
    Unset (None) counts as valid."""
    s = normalize_step_field(value)
    if s is None:
        return None, True
    if not DATE_RE.match(s):
        return s, False
    try:
        date.fromisoformat(s)
    except ValueError:
        return s, False
    return s, True


def _load_recheck_days() -> int:
    try:
        cfg = json.loads((REPO_ROOT / "config" / "agent-workability.json").read_text())
        return int(cfg["step_type_rules"]["check"]["recheck_after_days"])
    except (OSError, ValueError, KeyError, TypeError):
        return 7


RECHECK_AFTER_DAYS = _load_recheck_days()


def agent_step_state(item) -> dict:
    """Derived display state for an item's agent step (config/agent-workability.json).

    Works on sqlite row dicts and frontmatter dicts alike. States:
      invalid     as_of set but not a real YYYY-MM-DD date, or a step with a bad type
      unassessed  agent_step_as_of null
      none        as_of set, agent_next_step null
      investigate agent_step_type == investigate
      check       agent_step_type == check (check_due once as_of <= today - recheck days)
    """
    step = normalize_step_field(item.get("agent_next_step"))
    stype = normalize_step_field(item.get("agent_step_type"), lower=True)
    check = normalize_step_field(item.get("agent_step_check"))
    as_of_raw, as_of_ok = parse_as_of(item.get("agent_step_as_of"))
    as_of = date.fromisoformat(as_of_raw) if (as_of_raw and as_of_ok) else None

    if as_of_raw and not as_of_ok:
        state = "invalid"
    elif not as_of_raw:
        state = "unassessed"
    elif not step:
        state = "none"
    elif stype == "investigate":
        state = "investigate"
    elif stype == "check":
        state = "check"
    else:
        state = "invalid"

    check_due = bool(
        state == "check" and as_of is not None
        and as_of <= date.today() - timedelta(days=RECHECK_AFTER_DAYS)
    )

    badge, label = {
        "unassessed":  ("❔", "unassessed"),
        "none":        ("—", "no step"),
        "investigate": ("🔍", "investigate"),
        "check":       ("⏱", "check due" if check_due else "check (not yet due)"),
        "invalid":     ("❔", "invalid step fields"),
    }[state]

    return {
        "state": state,
        "badge": badge,
        "label": label,
        "check_due": check_due,
        "step": step,
        "step_type": stype,
        "check": check,
        "as_of": as_of_raw,
    }


def priority_dot(score: float) -> str:
    if score >= 75:
        return "🔴"
    if score >= 60:
        return "🟡"
    return "🟢"


def status_label(status: str, escalation: int) -> str:
    s = (status or "").lower()
    word = {
        "active": "Active", "monitoring": "Monitoring", "waiting": "Waiting",
        "backburner": "Backburner", "done": "Done",
    }.get(s, status or "—")
    if escalation >= 2:
        return f"⚠️ {word} (escalated)"
    if escalation == 1:
        return f"⚠️ {word} (flagged)"
    return word


def progress_cue(mention: int, progress: int, last_progress: str) -> str:
    # Filled blocks proportional to progress/mention, capped at 5.
    if mention <= 0:
        bar = "▱▱▱▱▱"
        ratio_txt = "no mentions"
    else:
        filled = max(0, min(5, round(5 * progress / mention)))
        bar = "▰" * filled + "▱" * (5 - filled)
        ratio_txt = f"{progress}/{mention} progressed"
    age = ""
    try:
        lp = date.fromisoformat(str(last_progress))
        days = (date.today() - lp).days
        age = f" · {days}d since progress"
    except (ValueError, TypeError):
        pass
    return f"{bar} {ratio_txt}{age}"


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))
