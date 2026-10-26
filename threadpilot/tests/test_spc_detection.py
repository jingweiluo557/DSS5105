"""The SPC study (docs/spc_detection.md) and the shipped stage alarm (simulation.briefing.stage_alarm). No browser needed.

The full study takes about six minutes, so it is not re-run here. Instead: the page must equal what the saved results render to,
the page's headline numbers must be the saved numbers, the shipped alarm must behave as the page says on hand-made series, and the
study's own rules must agree with the shipped function on generated series."""
import json
import random
from datetime import date, timedelta

from conftest import ROOT

from analysis import spc_detection as spc
from simulation import briefing

RESULTS = json.loads(spc.OUT.read_text(encoding="utf-8"))
DOC = spc.DOC.read_text(encoding="utf-8")


def test_the_page_is_what_the_saved_results_render_to():
    assert DOC == spc.render_doc(RESULTS), "run: python -m analysis.spc_detection --render"
    assert spc.SVG.read_text(encoding="utf-8") == spc.svg(RESULTS)


def test_the_headline_numbers_in_the_page_are_the_measured_ones():
    fa = RESULTS["false_alarms"]["per_month_factory"]
    assert round(fa["current"]) == 12 and "about\n**12 times a month" in DOC
    assert round(fa["3s_cusum"]) == 2 and "about **2 false alarms a month**" in DOC
    assert RESULTS["real_data"]["alarms_before_the_event"]["current"] == 25 and "fire 25 times on the real log" in DOC
    for e in RESULTS["detection"]["events"]:
        if e["drop_pct"] >= 30 and e["duration_workdays"] >= 3:
            assert e["3s_cusum"]["detected_pct"] == 100 and e["3s_cusum"]["mean_delay_workdays"] < 1, e
    assert RESULTS["real_data"]["assembly_event_first_flag"]["3s_cusum"] == "2026-03-25"


def log_from(values: list[int], stage: str = "PACKING") -> tuple[dict, list[date]]:
    days, day = [], date(2030, 1, 7)
    while len(days) < len(values):
        if day.weekday() != 6:
            days.append(day)
        day += timedelta(days=1)
    rows = {d: {"date": d.isoformat(), "stage": stage, "pieces_completed": v, "_file": "x", "_row": 0} for d, v in zip(days, values)}
    return {stage: rows}, days


def steady(n: int, seed: int = 1) -> list[int]:
    rng = random.Random(seed)
    return [round(700 * (1 + rng.gauss(0, 0.06))) for _ in range(n)]


def test_a_sudden_large_drop_is_raised_by_the_3_sigma_limit_on_its_first_day():
    values = steady(60) + [420]
    log, days = log_from(values)
    a = briefing.stage_alarm(log, "PACKING", days[-1])
    assert a["alarm"] and a["rule"] == "3-sigma" and a["z"] < -3


def test_a_small_sustained_drop_is_raised_by_cusum_and_not_by_3_sigma():
    values = steady(60) + [630] * 8          # 10% below a 700 mean, every day, SD about 42, so never past 3 SD
    log, days = log_from(values)
    flags = [briefing.stage_alarm(log, "PACKING", d) for d in days[-8:]]
    assert any(f["rule"] == "CUSUM" for f in flags), [f["cusum"] for f in flags]
    assert not any(f["rule"] == "3-sigma" for f in flags)


def test_an_ordinary_week_raises_nothing():
    log, days = log_from(steady(66, seed=3))
    assert not any(briefing.stage_alarm(log, "PACKING", d)["alarm"] for d in days[-6:])


def test_the_studys_rules_agree_with_the_shipped_function():
    model = spc.calibrate(spc.read_log())
    for k in range(3):
        out, days = spc.series(model, "WASHING", random.Random(f"agree|{k}"), {60 + i: 0.85 for i in range(6)})
        fired = spc.alarms(out, "WASHING", days)
        assert fired["3s_cusum"] == fired["shewhart_3s"] | fired["cusum"]
