"""The deny-token gate (scripts/scrub_check.py): the tracked tree is clean, and
the patterns catch what they claim to while leaving the template's own
vocabulary alone. Tokens are assembled by concatenation so this file does not
itself trip the gate."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scrub_check.py"


@pytest.fixture(scope="module")
def sc():
    spec = importlib.util.spec_from_file_location("scrub_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tracked_tree_is_clean(sc):
    hits = sc.scan_repo(ROOT)
    assert hits == [], "\n".join(str(h) for h in hits)


def test_self_is_the_only_exemption(sc):
    assert sc.SELF_EXEMPT == {"scripts/scrub_check.py"}


@pytest.mark.parametrize("text", [
    "ids = re.findall(r'(?:" + "ACO|" + "APP|" + "CO" + "|PRE)-')",   # the old regex
    "see " + "ACO" + "-016 and " + "DT" + "-023",            # old item IDs
    'labels = {"' + "app-" + 'checkout": "App & ' + 'Checkout"}',
    "ATL=mcp__" + "895f69c7-ac57-481d-983c-" + "2083485b3062",
    "look up docs/" + "contacts.md",
    "(ARCHITECTURE " + "§" + "12.4)",
    "ping someone@" + "realcompany" + ".com",
    "https://" + "realcompany" + ".atlassian.net/browse/X-1",
    "the " + "bes" + "tow repo",
])
def test_catches_known_leaks(sc, text):
    assert sc.scan_text(text), text


@pytest.mark.parametrize("text", [
    "- **[[ONB-001]]** — mention 5→5",                        # template item IDs
    "**ACMECHK-142** — Wallet pay events",                    # template Jira keys
    "ACMEPLT-90 and ACMEAH-1 are Jira keys, not items",       # guard: prefix embedded in a Jira key
    "https://example.atlassian.net/browse/ACMEONB-201",       # placeholder host
    "https://your-org.atlassian.net/mcp",                     # placeholder host
    "maintainer@example.com, ops@acme.example.com",           # placeholder emails
    "the engineer on the pre-signup bridge",                  # prose containing PRE
    "section § on its own is fine",
])
def test_leaves_template_vocabulary_alone(sc, text):
    assert sc.scan_text(text) == [], [str(h) for h in sc.scan_text(text)]


def test_cli_exit_codes(sc, tmp_path):
    (tmp_path / "clean.md").write_text("ONB-001 is fine\n")
    assert sc.main(["--root", str(tmp_path), "--quiet"]) == 0
    (tmp_path / "leak.md").write_text("docs/" + "contacts.md\n")
    assert sc.main(["--root", str(tmp_path), "--quiet"]) == 1
