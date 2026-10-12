"""The business-value simulation (docs/business_value.md). The full study takes about two minutes, so it is not re-run here.

Checked instead: the page equals what the saved results render to; its headline numbers are the saved ones; the three versions of
one future really are paired (identical with nothing planted, and a disruption that is never noticed changes nothing); and a
finding already on the page before a disruption began does not count as finding it."""
import json
from datetime import date

from conftest import ROOT  # noqa: F401  (puts the repository on the path)

from analysis import business_value as bv

RESULTS = json.loads(bv.OUT.read_text(encoding="utf-8"))
DOC = bv.DOC.read_text(encoding="utf-8")


def test_the_page_is_what_the_saved_results_render_to():
    assert DOC == bv.render_doc(RESULTS), "run: python -m analysis.business_value --render"


def test_the_headline_numbers_in_the_page_are_the_measured_ones():
    main = RESULTS["grid"][f"m{bv.MANUAL_LAG}_r{bv.RESPONSE_LAG}"]
    assert round(main["mean_days_avoided"]) == 30 and "about **30 working days of lateness**" in DOC
    assert (round(main["ci95"][0]), round(main["ci95"][1])) == (18, 43) and "(95% interval 18 to 43)" in DOC
    assert round(main["median_pct"], 1) == 3.5 and main["runs_worse"] == 7 and "in 7 of 40 futures" in DOC
    assert RESULTS["hit"]["runs_better"] == 37 and "37 of\n40 futures" in DOC
    assert round(RESULTS["grid"]["m3_r2"]["mean_days_avoided"]) == 16 and round(RESULTS["grid"]["m10_r1"]["mean_days_avoided"]) == 46
    assert sum(r["arms"]["m5_r2"]["by_hand"][0] > r["nobody"][0] for r in RESULTS["per_run"]) == 11 and "(in 11 of 40 futures)" in DOC
    assert RESULTS["detection"]["customer_hold"]["median_delay"] == 2 and RESULTS["detection"]["order_hold"]["median_delay"] == 5


def test_the_versions_of_one_future_are_paired():
    final_a, _ = bv.run(7, [])
    final_b, _ = bv.run(7, [])
    assert final_a == final_b, "same seed, nothing planted: identical futures"
    events = bv.plant(7)
    never = bv.cut(events, {}, 2)
    assert never == events, "a disruption nobody notices runs its full length"
    noticed = {events[0]["id"]: date.fromisoformat(events[0]["start"])}
    shorter = bv.cut(events, noticed, 2)
    assert shorter[0]["end"] < events[0]["end"] and shorter[1:] == events[1:]


def test_a_finding_already_on_the_page_does_not_count_as_finding_a_new_disruption():
    _, shown = bv.run(1, bv.plant(1), mornings=True)
    for ev in bv.plant(1):
        if ev["id"] in shown:
            assert shown[ev["id"]] > date.fromisoformat(ev["start"])
