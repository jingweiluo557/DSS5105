"""The invented-number check (evaluation/provenance.py): its rules on hand-made answers, and the saved runs the docs quote. No browser."""
import json

from conftest import ROOT

from evaluation.provenance import check

RESULTS = ROOT / "evaluation" / "results"


def tool(*objs) -> str:
    return json.dumps([{"name": "t", "result": o} for o in objs])


def test_a_number_a_tool_returned_is_traced_and_one_it_did_not_is_flagged():
    r = check("8 orders are late and 3 more will be.", "Which orders are late?", tool({"late": 8}))
    assert r["traced"] == 1 and r["untraced"] == ["3"]


def test_a_total_of_one_result_and_a_list_length_count_as_traced():
    r = check("34 orders are in progress: 8 late, 26 at risk, 0 on track.", "", tool({"late": 8, "at_risk": 26, "on_track": 0}))
    assert r["untraced"] == []
    assert check("2 orders: ORD-001 and ORD-002.", "", tool([{"id": "ORD-001"}, {"id": "ORD-002"}]))["untraced"] == []


def test_a_date_the_tool_resolved_to_another_year_is_flagged_even_if_the_manager_named_it():
    """The Q31 defect: "by 20 March" on 1 April was read as 20 March 2027. The day and month were echoed from the question, so only
    the year betrays it."""
    r = check("Possible only if it is prioritised by Sat, 20 Mar.", "Can we take 200 beanies by 20 March?", tool({"due": "2027-03-20"}))
    assert r["untraced"] and "2027-03-20" in r["untraced"][0]


def test_order_ids_and_product_rules_are_not_counted_as_figures():
    r = check("ORD-120 is due in 0 days; the briefing runs at 07:00 on the previous 8 same weekdays.", "", tool({"days_to_due": 0}))
    assert r["untraced"] == [] and r["product"] == 2


def test_the_saved_runs_say_what_the_docs_say():
    first = json.loads((RESULTS / "provenance_first_run.json").read_text(encoding="utf-8"))
    latest = json.loads((RESULTS / "provenance.json").read_text(encoding="utf-8"))
    assert first["bait"]["summary"]["passed"] == 10 and first["bait"]["summary"]["total"] == 16
    assert {u["id"] for u in first["untraced"]} == {"Q01", "Q31", "H01"}
    assert latest["bait"]["summary"]["passed"] == 16 and all(s["untraced"] == 0 for s in latest["sets"].values())
    doc = (ROOT / "docs" / "evaluation.md").read_text(encoding="utf-8")
    assert "**10 of 16**" in doc and "3 of 163" in doc
