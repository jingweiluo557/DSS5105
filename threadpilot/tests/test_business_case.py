"""The business case document shows exactly what analysis/business_case.py computes from its stated inputs."""
import json

from conftest import ROOT

from analysis import business_case as bc


def test_the_document_tables_come_from_the_saved_results():
    saved = json.loads((ROOT / "analysis/results/business_case.json").read_text())
    doc = (ROOT / "docs/business_case.md").read_text(encoding="utf-8")
    assert bc.tables(saved) in doc
    assert saved["inputs"] == json.loads(json.dumps(bc.INPUTS))


def test_the_lateness_line_is_the_paired_simulation_priced_per_order_day():
    saved = json.loads((ROOT / "analysis/results/business_case.json").read_text())
    sim = json.loads((ROOT / "analysis/results/business_value.json").read_text())
    days = sim["grid"]["m5_r2"]["mean_days_avoided"]
    assert saved["lateness"]["days_avoided_per_2_months"] == days == 30.5
    expected = days * saved["avg_order_value_usd"] * bc.INPUTS["late_penalty_per_working_day"] * bc.INPUTS["usd_to_sgd"] * 6
    assert abs(saved["lateness"]["value_year_sgd"]["mean"] - expected) < 200


def test_the_same_seed_gives_the_same_hours():
    import random
    a = [bc.labour(random.Random(5105)) for _ in range(3)]
    b = [bc.labour(random.Random(5105)) for _ in range(3)]
    assert a == b and all(before > after > 0 for before, after in a)
