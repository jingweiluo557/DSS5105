"""Are the risk levels and the feasibility ranges honest? Calibration, discrimination and sharpness against simulated futures.

The briefing labels every order overdue / high / medium / low, and the chat answers "Can we take N pieces by date?" with a range
(best case to cautious case). Two earlier checks looked good: high-risk orders were late 93% of the time, and the real finish fell
inside the feasibility range 14 times out of 14. Both can flatter: if nearly every order is late, "high" is right by default; and
a range wide enough contains everything. This study asks the sharper questions.

Risk levels
    Many independent simulated futures (different random seeds, no planted events), mornings from day 0 to day 110, so the factory
    goes from badly behind to caught up and every level occurs. For each order on each morning: its level that morning, and whether
    it actually finished late in that future (simulated 400 days ahead).
    * calibration: the share finished late, per level, with a 95% Wilson interval
    * discrimination: AUC, the chance that a randomly chosen late order was given a higher predicted lateness than a randomly chosen
      on-time one. The model's score (working days late in the expected case) against a naive score (fewer days to the due date =
      more likely late). Overdue orders are left out: they are late by definition.
    * the expected finish date against the real one, by how far ahead it was made

Feasibility ranges (the chat's own JavaScript tool, run in the real page on each simulated morning)
    A test order (400 to 1,500 pieces, due 14 to 70 days out) is injected into the same future as a real order, and its real finish
    is compared with the range the chat gave for it that morning.
    * coverage: how often the real finish is inside [best, cautious]; width of the range in working days
    * a naive range for comparison: the 10th to 90th percentile of how long orders that finished in the last 60 days took
    * verdicts: how often an order finished by its date, per verdict

    python -m analysis.calibration            # about two minutes; writes analysis/results/calibration.json
    python -m analysis.calibration --render   # only redraws docs/calibration.md from the saved results

Limits: the simulator is not a real factory, and it schedules earliest-due-first like the projection engine, so agreement here
is the best case. Mornings of the same future share orders, so the order-mornings are not independent; the intervals are a guide.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from simulation.briefing import build
from simulation.simulate import simulate
from simulation.workdays import working_days_between, working_days_inclusive

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "results" / "calibration.json"
DOC = ROOT / "docs" / "calibration.md"
SVG = ROOT / "docs" / "images" / "calibration_risk.svg"
DEMO = ROOT / "demo" / "briefing_demo.html"
BASE = date(2026, 4, 1)
HORIZON = 400
SEEDS = range(1, 31)                      # 30 independent futures for the risk levels
MORNINGS = (0, 10, 20, 30, 40, 50, 60, 75, 90, 110)
FEAS_SEEDS = range(101, 113)              # 12 futures for the feasibility test orders
FEAS_MORNINGS = (0, 20, 40, 60, 90)
FEAS_PER_MORNING = 3
LEVELS = ["overdue", "high", "medium", "low"]


def _scenario(seed: int, events: list | None = None) -> Path:
    p = Path(tempfile.mkdtemp()) / "scenario.json"
    p.write_text(json.dumps({"seed": seed, "events": events or []}), encoding="utf-8")
    return p


def _orders(folder: Path) -> dict[str, dict]:
    import csv
    with (folder / "orders.csv").open(newline="", encoding="utf-8") as f:
        return {r["order_id"]: r for r in csv.DictReader(f)}


def _morning(seed_path: Path, m: int) -> tuple[Path, date]:
    day = BASE + timedelta(days=m)
    out = Path(tempfile.mkdtemp())
    simulate(day, out=out, scenario_path=seed_path)
    return out, day


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (float("nan"), float("nan"))
    z, p = 1.96, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(100 * (centre - half), 1), round(100 * (centre + half), 1))


def auc(scores_pos: list[float], scores_neg: list[float]) -> float:
    """Mann-Whitney AUC: P(score of a late order > score of an on-time order), ties counted half."""
    if not scores_pos or not scores_neg:
        return float("nan")
    allv = sorted([(s, 1) for s in scores_pos] + [(s, 0) for s in scores_neg])
    ranks, i = {}, 0
    rank_sum = 0.0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + 1 + j) / 2
        rank_sum += r * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    n1, n0 = len(scores_pos), len(scores_neg)
    return round((rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0), 3)


# ---------------------------------------------------------------- risk levels
def risk_study() -> dict:
    rows = []
    for seed in SEEDS:
        sp = _scenario(seed)
        final_dir = Path(tempfile.mkdtemp())
        simulate(BASE + timedelta(days=HORIZON), out=final_dir, scenario_path=sp)
        final = _orders(final_dir)
        for m in MORNINGS:
            folder, day = (ROOT / "data", BASE) if m == 0 else _morning(sp, m)
            b = build(folder, day)
            for o in b["orders"]:
                f = final[o["order_id"]]
                done = f["completed_date"] or None
                late = (done is None) or done > o["due_date"]
                r = o["risk"]
                err = None
                if done and r.get("expected_date"):
                    e, a = date.fromisoformat(r["expected_date"]), date.fromisoformat(done)
                    err = working_days_between(e, a)          # positive = finished later than expected
                rows.append({"seed": seed, "morning": m, "order": o["order_id"], "level": r["level"], "confidence": r["confidence"],
                             "late": late, "score": r.get("late_days_expected") if r.get("late_days_expected") is not None else 99,
                             "days_to_due": o["days_to_due"], "error": err,
                             "ahead": working_days_inclusive(day, date.fromisoformat(r["expected_date"])) if r.get("expected_date") else None})
    out = {"order_mornings": len(rows), "futures": len(SEEDS), "mornings": list(MORNINGS),
           "distinct_orders": len({(r["seed"], r["order"]) for r in rows}), "levels": {}, "confidence": {}}
    for lvl in LEVELS:
        sel = [r for r in rows if r["level"] == lvl]
        k = sum(r["late"] for r in sel)
        out["levels"][lvl] = {"n": len(sel), "late": k, "late_pct": round(100 * k / len(sel), 1) if sel else None, "ci95": wilson(k, len(sel))}
    judged = [r for r in rows if r["level"] != "overdue"]
    for c in ("high", "medium", "low"):
        sel = [r for r in judged if r["confidence"] == c]
        right = sum((r["level"] in ("high", "medium")) == r["late"] for r in sel)
        out["confidence"][c] = {"n": len(sel), "call_right": right, "pct": round(100 * right / len(sel), 1) if sel else None}
    pos, neg = [r for r in judged if r["late"]], [r for r in judged if not r["late"]]
    out["auc_model"] = auc([r["score"] for r in pos], [r["score"] for r in neg])
    out["auc_naive_days_to_due"] = auc([-r["days_to_due"] for r in pos], [-r["days_to_due"] for r in neg])
    out["late_share_not_overdue"] = round(100 * len(pos) / len(judged), 1)
    buckets = [("up to 10", 0, 10), ("11 to 25", 11, 25), ("over 25", 26, 10**6)]
    out["finish_error"] = []
    for name, lo, hi in buckets:
        e = [r["error"] for r in rows if r["error"] is not None and r["ahead"] is not None and lo <= r["ahead"] <= hi]
        if e:
            out["finish_error"].append({"ahead_workdays": name, "n": len(e), "mean": round(st.mean(e), 1), "mae": round(st.mean(abs(x) for x in e), 1),
                                        "within_2_pct": round(100 * sum(abs(x) <= 2 for x in e) / len(e), 1)})
    return out


# ---------------------------------------------------------------- feasibility ranges
JS_FEAS = """([briefing, pieces, due]) => {
  B.push(briefing); idx = B.length - 1;
  const r = ThreadPilotChat.tools.check_feasibility.run({pieces, due});
  B.pop(); idx = B.length - 1;
  return r.error ? {error: r.error} : {best: r.best, cautious: r.cautious, low: r.low, high: r.high, widen: r.widen, verdict: r.verdict, W: r.W};
}"""


def feasibility_study() -> dict:
    from playwright.sync_api import sync_playwright
    cases = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(DEMO.as_uri())
        page.wait_for_selector("#riskCard .rk-col")
        for seed in FEAS_SEEDS:
            rng = random.Random(seed)
            sp = _scenario(seed)
            for m in FEAS_MORNINGS:
                day = BASE + timedelta(days=m)
                folder, _ = (ROOT / "data", BASE) if m == 0 else _morning(sp, m)
                b = build(folder, day)
                done60 = []
                for o in _orders(folder).values():
                    if o["status"] == "COMPLETE" and o["completed_date"] and date.fromisoformat(o["completed_date"]) >= day - timedelta(days=60):
                        done60.append(working_days_inclusive(date.fromisoformat(o["order_date"]), date.fromisoformat(o["completed_date"])))
                done60.sort()
                for _ in range(FEAS_PER_MORNING):
                    pieces, lead = rng.choice([400, 600, 800, 1000, 1200, 1500]), rng.randint(14, 70)
                    due = (day + timedelta(days=lead)).isoformat()
                    est = page.evaluate(JS_FEAS, [b, pieces, due])
                    if "error" in est:
                        continue
                    arrive = day if day.weekday() != 6 else day + timedelta(days=1)   # the factory is closed on Sundays: it arrives Monday
                    ev = {"id": "T", "type": "rush_order", "date": arrive.isoformat(), "customer": "Test Co", "product": "Hoodie",
                          "category": "TOPS", "pieces": pieces, "lead_days": (date.fromisoformat(due) - arrive).days}
                    out = Path(tempfile.mkdtemp())
                    simulate(BASE + timedelta(days=HORIZON), out=out, scenario_path=_scenario(seed, [ev]))
                    mine = [o for o in _orders(out).values() if o["customer"] == "Test Co" and o["order_date"] == arrive.isoformat()]
                    assert len(mine) == 1, mine
                    fin = mine[0]["completed_date"] or None
                    actual = working_days_inclusive(day, date.fromisoformat(fin)) if fin else None
                    q = lambda pct: done60[min(len(done60) - 1, int(pct * len(done60)))] if done60 else None
                    cases.append({"seed": seed, "morning": m, "pieces": pieces, "lead_days": lead, "W": est["W"], "best": est["best"],
                                  "cautious": est["cautious"], "low": est["low"], "high": est["high"], "verdict": est["verdict"], "actual": actual,
                                  "naive": [q(0.1), q(0.9)], "on_time": actual is not None and actual <= est["W"]})
        browser.close()
    finished = [c for c in cases if c["actual"] is not None]
    closed = [c for c in finished if c["cautious"] is not None]
    inside = [c for c in closed if c["best"] <= c["actual"] <= c["cautious"]]
    naive = [c for c in finished if c["naive"][0] is not None]
    out = {"cases": len(cases), "finished": len(finished), "open_ended": sum(c["cautious"] is None for c in cases),
           "coverage": {"n": len(closed), "inside": len(inside), "pct": round(100 * len(inside) / len(closed), 1) if closed else None,
                        "ci95": wilson(len(inside), len(closed)),
                        "below_best": sum(c["actual"] < c["best"] for c in closed), "after_cautious": sum(c["actual"] > c["cautious"] for c in closed)},
           "width": {"median": st.median(c["cautious"] - c["best"] for c in closed) if closed else None,
                     "median_relative_pct": round(100 * st.median((c["cautious"] - c["best"]) / c["actual"] for c in closed), 0) if closed else None},
           "position_median": round(st.median((c["actual"] - c["best"]) / max(1, c["cautious"] - c["best"]) for c in inside), 2) if inside else None,
           "naive": {"n": len(naive), "inside": sum(c["naive"][0] <= c["actual"] <= c["naive"][1] for c in naive),
                     "pct": round(100 * sum(c["naive"][0] <= c["actual"] <= c["naive"][1] for c in naive) / len(naive), 1) if naive else None,
                     "median_width": st.median(c["naive"][1] - c["naive"][0] for c in naive) if naive else None},
           "verdicts": {}}
    for v in ("likely", "tight", "only_if_prioritised", "unlikely"):
        sel = [c for c in cases if c["verdict"] == v]
        k = sum(c["on_time"] for c in sel)
        out["verdicts"][v] = {"n": len(sel), "on_time": k, "pct": round(100 * k / len(sel), 1) if sel else None, "ci95": wilson(k, len(sel))}
    out["conformal"] = conformal(closed)
    widened = [c for c in closed if c["high"] is not None]
    out["shipped"] = {"widen": cases[0]["high"] - cases[0]["cautious"] if cases and cases[0]["high"] is not None else None, "n": len(widened),
                      "inside_pct": round(100 * sum(c["low"] <= c["actual"] <= c["high"] for c in widened) / len(widened), 1) if widened else None,
                      "median_width": st.median(c["high"] - c["low"] for c in widened) if widened else None}
    out["examples"] = cases
    return out


def conformal(closed: list[dict]) -> list[dict]:
    """Split-conformal widening: learn from the first half of the futures how far outside the range real finishes fall, widen the
    range by that much, and measure coverage on the other half (never seen while learning)."""
    seeds = sorted({c["seed"] for c in closed})
    learn, test = [c for c in closed if c["seed"] in seeds[: len(seeds) // 2]], [c for c in closed if c["seed"] in seeds[len(seeds) // 2:]]
    score = lambda c: max(c["best"] - c["actual"], c["actual"] - c["cautious"], 0)
    s = sorted(score(c) for c in learn)
    rows = [{"target_pct": None, "widen_by": 0, "test_n": len(test),
             "test_inside_pct": round(100 * sum(c["best"] <= c["actual"] <= c["cautious"] for c in test) / len(test), 1),
             "median_width": st.median(c["cautious"] - c["best"] for c in test)}]
    for target in (80, 90):
        k = min(len(s) - 1, math.ceil((len(s) + 1) * target / 100) - 1)
        q = s[k]
        inside = sum(c["best"] - q <= c["actual"] <= c["cautious"] + q for c in test)
        rows.append({"target_pct": target, "widen_by": q, "test_n": len(test), "test_inside_pct": round(100 * inside / len(test), 1),
                     "median_width": st.median(c["cautious"] - c["best"] + 2 * q for c in test)})
    return rows


# ---------------------------------------------------------------- the page
START, END = "<!-- calibration:start (generated by analysis/calibration.py from analysis/results/calibration.json) -->", "<!-- calibration:end -->"
VERDICT = {"likely": "Likely feasible", "tight": "Feasible but tight", "only_if_prioritised": "Possible only if prioritised", "unlikely": "Unlikely"}


def pct(x) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:g}%"


def markdown(r: dict) -> str:
    k, f = r["risk"], r["feasibility"]
    out = [f"### Risk levels: what share actually finished late\n",
           f"{k['order_mornings']:,} order-mornings: {k['distinct_orders']:,} orders in {k['futures']} simulated futures, judged on mornings "
           f"{', '.join(str(m) for m in k['mornings'])} days after 1 April.\n",
           "| Level | Order-mornings | Finished late | 95% interval |", "|---|---|---|---|"]
    for lvl in LEVELS:
        x = k["levels"][lvl]
        out.append(f"| {lvl} | {x['n']:,} | {pct(x['late_pct'])} | {x['ci95'][0]:g} to {x['ci95'][1]:g}% |" if x["n"] else f"| {lvl} | 0 | n/a | n/a |")
    out += ["", f"Discrimination, overdue orders left out ({pct(k['late_share_not_overdue'])} of the rest finished late): "
                f"AUC **{k['auc_model']}** for the model's expected lateness, against **{k['auc_naive_days_to_due']}** for the naive rule "
                "\"the sooner it is due, the likelier it is late\". 0.5 is a coin toss, 1.0 is perfect.\n",
            "| Confidence label | Order-mornings | Late-or-not call right |", "|---|---|---|"]
    for c in ("high", "medium", "low"):
        x = k["confidence"][c]
        out.append(f"| {c} | {x['n']:,} | {pct(x['pct'])} |")
    out += ["", "Expected finish date against the real one (positive = later than expected):\n",
            "| Made this far ahead (working days) | Orders | Mean error | Mean absolute error | Within 2 working days |", "|---|---|---|---|---|"]
    for e in k["finish_error"]:
        out.append(f"| {e['ahead_workdays']} | {e['n']:,} | {e['mean']:+g} | {e['mae']:g} | {pct(e['within_2_pct'])} |")
    cv = f["coverage"]
    out += ["", "### Feasibility ranges: right, and how wide\n",
            f"{f['cases']} test orders injected into {len(list(FEAS_SEEDS))} simulated futures on mornings {', '.join(str(m) for m in FEAS_MORNINGS)}; "
            f"{f['finished']} finished within the {HORIZON}-day horizon; {f['open_ended']} ranges had no cautious end (the chat said it might not finish "
            "within 200 working days if new orders keep going ahead).\n",
            "| Range | Cases | Real finish inside | Median width (working days) |", "|---|---|---|---|",
            f"| The chat's range, best case to cautious case | {cv['n']} | {cv['inside']} ({pct(cv['pct'])}; 95% {cv['ci95'][0]:g} to {cv['ci95'][1]:g}%) | {f['width']['median']:g} |",
            f"| Naive: 10th to 90th percentile of recent order lead times | {f['naive']['n']} | {f['naive']['inside']} ({pct(f['naive']['pct'])}) | {f['naive']['median_width']:g} |",
            "", f"Outside the chat's range: {cv['below_best']} finished before the best case, {cv['after_cautious']} after the cautious case. "
                f"The median range is {f['width']['median_relative_pct']:g}% of the real time taken; inside the range, the real finish sits at "
                f"{f['position_median']:g} of the way from best to cautious (0 = best case).\n",
            "Widening the range so it covers what it claims (split-conformal: learned on half of the futures, tested on the other half):\n",
            "| Target coverage | Widen each end by (working days) | Real finish inside, held-out half | Median width (working days) |", "|---|---|---|---|"]
    for c in f["conformal"]:
        out.append(f"| {'unwidened (before)' if c['target_pct'] is None else str(c['target_pct']) + '%'} | {c['widen_by']} | {pct(c['test_inside_pct'])} of {c['test_n']} | {c['median_width']:g} |")
    s = f["shipped"]
    out += ["", f"The chat now shows the range widened by {s['widen']} working days at each end. On all {s['n']} cases (half of them used to choose the 3) "
                f"the real finish is inside {pct(s['inside_pct'])} of the time, median width {s['median_width']:g} working days; the held-out figure above is the one to quote.\n",
            "| Verdict given | Cases | Finished by the date | 95% interval |", "|---|---|---|---|"]
    for v, x in f["verdicts"].items():
        out.append(f"| {VERDICT[v]} | {x['n']} | {pct(x['pct'])} | {x['ci95'][0]:g} to {x['ci95'][1]:g}% |" if x["n"] else f"| {VERDICT[v]} | 0 | n/a | n/a |")
    return "\n".join(out) + "\n"


def svg(r: dict) -> str:
    """Share finished late per risk level, with 95% intervals."""
    k = r["risk"]["levels"]
    W, H, L, T, row, RM = 640, 256, 90, 24, 44, 150
    X = lambda v: L + (W - L - RM) * v / 100
    ink, muted, grid, bar = "#16262B", "#5E6E7A", "#D5DEE0", "#2E6F77"
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" font-family="Calibri, Arial, sans-serif">',
             "<title>Share of orders that finished late, by the risk level they were given, with 95% intervals</title>",
             f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    for v in range(0, 101, 25):
        parts.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{T - 6}" y2="{T + row * 4}" stroke="{grid}"/>')
        parts.append(f'<text x="{X(v):.1f}" y="{T + row * 4 + 16}" text-anchor="middle" font-size="12" fill="{muted}">{v}%</text>')
    for i, lvl in enumerate(LEVELS):
        x = k[lvl]
        y = T + i * row + 8
        parts.append(f'<text x="{L - 10}" y="{y + 15}" text-anchor="end" font-size="13" fill="{ink}">{lvl}</text>')
        if not x["n"]:
            continue
        parts.append(f'<rect x="{X(0):.1f}" y="{y}" width="{X(x["late_pct"]) - X(0):.1f}" height="22" rx="4" fill="{bar}">'
                     f'<title>{lvl}: {x["late_pct"]}% late of {x["n"]}</title></rect>')
        lo, hi = x["ci95"]
        parts.append(f'<line x1="{X(lo):.1f}" x2="{X(hi):.1f}" y1="{y + 11}" y2="{y + 11}" stroke="{ink}" stroke-width="2"/>')
        parts.append(f'<text x="{X(max(hi, x["late_pct"])) + 8:.1f}" y="{y + 15}" font-size="12" fill="{ink}">{x["late_pct"]:g}% (n={x["n"]:,})</text>')
    parts.append(f'<text x="{(L + W - RM) / 2}" y="{H - 8}" text-anchor="middle" font-size="13" fill="{ink}">Share that finished late</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_doc(r: dict) -> str:
    text = DOC.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n\n{markdown(r)}\n{END}{tail}"


def main() -> None:
    if "--render" not in sys.argv:
        r = {"risk": risk_study(), "feasibility": feasibility_study()}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8")
    r = json.loads(OUT.read_text(encoding="utf-8"))
    if DOC.exists():
        DOC.write_text(render_doc(r), encoding="utf-8")
        SVG.write_text(svg(r), encoding="utf-8")
    print(markdown(r))


if __name__ == "__main__":
    main()
