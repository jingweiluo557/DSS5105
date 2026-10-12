"""docs/alert_triggers.md must say what the code does. No browser needed.

Every constant, score formula, ranking rule and loop interval in the page is read back from the code or the shipped briefings.
If one changes, this test fails until the page is updated, so the page cannot quietly go stale.
"""
import json
import re

import pytest
from conftest import ROOT

from simulation import briefing

DOC = (ROOT / "docs" / "alert_triggers.md").read_text(encoding="utf-8")
SOURCE = (ROOT / "simulation" / "briefing.py").read_text(encoding="utf-8")
SHIPPED = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "briefings").glob("*.json"))]


@pytest.mark.parametrize("name", ["BASELINE_WEEKS", "MIN_SAMPLES", "BAND_SD", "BAND_MIN_PCT", "SPC_SIGMA", "CUSUM_K", "CUSUM_H", "IDLE_ALERT", "DUE_SOON", "TOP_N"])
def test_constants_table_matches_the_code(name):
    value = getattr(briefing, name)
    assert re.search(rf"\| `{name}` \| {re.escape(str(value))} \|", DOC), f"{name} = {value} is not in the constants table"


def test_every_score_reason_in_the_briefings_is_in_the_page():
    seen = {(f["type"], f["score_reason"]) for b in SHIPPED for f in b["all_findings"]}
    assert len(seen) >= 8
    for kind, reason in seen:
        assert f"`{kind}`" in DOC and reason in DOC, f"{kind}: {reason}"


def test_every_finding_type_and_next_step_is_in_the_page():
    block = SOURCE.split("NEXT_STEP = {", 1)[1].split("}\n", 1)[0]
    pairs = re.findall(r'"(\w+)": \("([^"]+)"', block)
    assert len(pairs) == 8
    for kind, step in pairs:
        row = next((line for line in DOC.splitlines() if line.startswith(f"| `{kind}` |")), None)
        assert row, kind
        assert step in row, f"{kind}: next step '{step}'"


def test_ranking_rule_and_reasons_are_quoted_exactly():
    assert briefing.DEFINITIONS["ranking"] in DOC
    for b in SHIPPED[:1]:
        assert b["definitions"]["ranking"] == briefing.DEFINITIONS["ranking"]
    assert "new since yesterday (+10)" in DOC and "getting worse (no fade)" in DOC and "first briefing" in DOC
    assert "**+10**" in DOC and "**-4 for every extra morning**" in DOC and "up to **-20**" in DOC and "**8 or more points worse**" in DOC
    # the numbers above are the ones in the code
    assert 'f["score"] >= before["score"] + 8' in SOURCE
    assert '(10 if f["is_new"] else 0)' in SOURCE and "min(20, 4 * (f[\"open_days\"] - 1))" in SOURCE


def test_severity_thresholds_match_the_code():
    assert 'f["rank_score"] >= 80 else "high" if f["rank_score"] >= 65 else "watch"' in SOURCE
    assert "**critical** at 80 or above" in DOC and "**high** at 65 or above" in DOC


def test_backend_loop_and_confirmation_numbers_match_the_code():
    api = (ROOT / "backend" / "app" / "workflow_api.py").read_text(encoding="utf-8")
    engine = (ROOT / "backend" / "app" / "workflow_engine.py").read_text(encoding="utf-8")
    assert "await asyncio.sleep(30)" in api and "every **30 seconds**" in DOC
    assert "timedelta(minutes=15)" in engine
    actions = (ROOT / "docs" / "actions_and_limits.md").read_text(encoding="utf-8")
    assert "expires after 15 minutes" in actions


def test_counts_quoted_for_the_shipped_mornings_are_true():
    found = sum(len(b["all_findings"]) for b in SHIPPED)
    shown = sum(len(b["findings"]) for b in SHIPPED)
    assert (len(SHIPPED), found, shown, found - shown) == (15, 101, 74, 27)
    assert f"{found} findings, showed {shown} and counted the other {found - shown}" in DOC
    assert max(len(b["findings"]) for b in SHIPPED) == briefing.TOP_N
    per_day = [len(b["all_findings"]) for b in SHIPPED]
    assert (min(per_day), max(per_day)) == (4, 9) and "between\n  4 and 9 found each morning" in DOC


def test_watch_kinds_in_the_page_are_the_ones_the_chat_creates():
    chat = (ROOT / "simulation" / "chat.js").read_text(encoding="utf-8")
    for kind in ("no_move", "stage_behind", "plain"):
        assert f'"{kind}"' in chat and f"| `{kind}` |" in DOC
