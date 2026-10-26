"""The calibration study (docs/calibration.md) and the widening it chose for the chat's feasibility range. No browser needed.

The study takes about a minute and needs a browser, so it is not re-run here. Instead: the page must equal what the saved results
render to, its headline numbers must be the saved ones, the chat must use the widening the held-out test chose, and the two
statistics helpers must be right on cases worked by hand."""
import json
import re

from conftest import ROOT

from analysis import calibration as cal

RESULTS = json.loads(cal.OUT.read_text(encoding="utf-8"))
DOC = cal.DOC.read_text(encoding="utf-8")


def test_the_page_is_what_the_saved_results_render_to():
    assert DOC == cal.render_doc(RESULTS), "run: python -m analysis.calibration --render"
    assert cal.SVG.read_text(encoding="utf-8") == cal.svg(RESULTS)


def test_the_headline_numbers_in_the_page_are_the_measured_ones():
    k, f = RESULTS["risk"], RESULTS["feasibility"]
    assert round(k["levels"]["high"]["late_pct"]) == 96 and round(k["levels"]["low"]["late_pct"]) == 4
    assert round(k["auc_model"], 2) == 0.98 and round(k["auc_naive_days_to_due"], 2) == 0.67
    assert "AUC of 0.98" in DOC and "0.67 for" in DOC
    assert 65 <= f["coverage"]["pct"] <= 75 and "about 7 times in 10" in DOC
    ninety = next(c for c in f["conformal"] if c["target_pct"] == 90)
    assert round(ninety["test_inside_pct"]) == 94 and "**94%**" in DOC
    assert f["verdicts"]["likely"]["pct"] == 100 and round(f["verdicts"]["unlikely"]["pct"]) == 23


def test_the_chat_uses_the_widening_the_held_out_test_chose():
    js = (ROOT / "simulation" / "chat.js").read_text(encoding="utf-8")
    widen = int(re.search(r"const RANGE_WIDEN = (\d+);", js)[1])
    ninety = next(c for c in RESULTS["feasibility"]["conformal"] if c["target_pct"] == 90)
    assert widen == ninety["widen_by"] == RESULTS["feasibility"]["shipped"]["widen"]


def test_auc_and_wilson_on_hand_worked_cases():
    assert cal.auc([3, 4], [1, 2]) == 1.0 and cal.auc([1, 2], [3, 4]) == 0.0
    assert cal.auc([1, 1], [1, 1]) == 0.5                       # all ties: a coin toss
    assert cal.auc([2, 4], [1, 3]) == 0.75                      # 3 of 4 pairs ordered right
    lo, hi = cal.wilson(50, 100)
    assert lo < 50 < hi and abs((50 - lo) - (hi - 50)) < 0.2 and 40 < lo < 41
