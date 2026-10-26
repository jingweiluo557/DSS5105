"""What is the co-pilot worth? A paired simulation: the same factory, the same disruptions, found by the briefing or found by hand.

No real general manager has used ThreadPilot, so "time saved" cannot be measured. This study measures the next best thing, in
simulation, and says so: how much lateness is avoided when problems are found by the morning briefing instead of by the usual
routine, if the manager then acts on them.

Each run is one simulated future (its own random seed) with six planted disruptions of known start and length: two customers whose
orders all stop (a supplier or approval hold), two single orders that stop, and two stages that slow down (a breakdown). Then three
versions of that SAME future are simulated, identical in every random draw:

    nobody acts     every disruption runs its full length
    by hand         each disruption is noticed MANUAL_LAG working days after it starts (a weekly review, a customer calling),
                    and ends RESPONSE_LAG working days after that (the chase, the repair)
    co-pilot        each disruption is noticed on the first morning the briefing shows a finding for it in its top five, and
                    ends RESPONSE_LAG working days after that. A disruption the briefing never shows is noticed by hand.

"Shows a finding for it" is decided by code: a customer hold matches `customer_stalled:<customer>` or a quiet-order finding that
names one of its orders; an order hold matches a quiet-order finding (or its customer stalling); a slowdown matches
`stage_below:<stage>`. Outcome: working days late summed over every order that is in progress or arrives in the first 60 days,
followed until it finishes.

    python -m analysis.business_value              # about two minutes; writes analysis/results/business_value.json
    python -m analysis.business_value --render     # only redraws docs/business_value.md from the saved results

Limits, stated in the page: every number depends on the assumed lags, so the page shows how the result moves with them; acting on a
false alarm costs time that is not modelled; the simulator is not a real factory.
"""
from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
from datetime import date, timedelta
from pathlib import Path

from simulation import briefing
from simulation.simulate import BASE_DIR, Factory
from simulation.workdays import add_working_days, is_working, working_days_between

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "results" / "business_value.json"
DOC = ROOT / "docs" / "business_value.md"
BASE = date(2026, 4, 1)
RUNS = 40
WINDOW = 60                 # disruptions start in the first ~45 days; orders in progress or arriving in the first 60 days are scored
HORIZON = 260               # long enough for every scored order to finish
MANUAL_LAG, RESPONSE_LAG = 5, 2
SENSITIVITY = {"manual": (3, 5, 10), "response": (1, 2, 4)}


# ---------------------------------------------------------------- one future
def plant(seed: int) -> list[dict]:
    """Six disruptions with known start and length (in calendar days; the simulator applies them on working days)."""
    rng = random.Random(f"value|{seed}")
    f = Factory(BASE_DIR, {"seed": seed, "events": []})
    active = [o for o in f.orders if o["status"] == "IN_PROGRESS"]
    customers = sorted({o["customer"] for o in active})
    events = []
    for i, cust in enumerate(rng.sample(customers, 2)):
        start = BASE + timedelta(days=rng.randint(3, 40))
        events.append({"id": f"C{i}", "type": "customer_hold", "customer": cust, "start": start.isoformat(),
                       "end": (start + timedelta(days=rng.randint(10, 20))).isoformat()})
    held = {e["customer"] for e in events}
    for i, o in enumerate(rng.sample([o for o in active if o["customer"] not in held], 2)):
        start = BASE + timedelta(days=rng.randint(1, 15))
        events.append({"id": f"O{i}", "type": "order_hold", "order_id": o["order_id"], "start": start.isoformat(),
                       "end": (start + timedelta(days=rng.randint(10, 20))).isoformat()})
    for i, stage in enumerate(rng.sample(briefing.STAGES, 2)):
        start = BASE + timedelta(days=rng.randint(3, 45))
        events.append({"id": f"S{i}", "type": "stage_slowdown", "stage": stage, "factor": round(rng.uniform(0.45, 0.75), 2),
                       "start": start.isoformat(), "end": (start + timedelta(days=rng.randint(4, 10))).isoformat()})
    return events


def run(seed: int, events: list[dict], mornings: bool = False) -> tuple[dict[str, dict], dict[str, date]]:
    """Simulate to the horizon. With `mornings`, also build the briefing every morning and record when each event is first shown."""
    f = Factory(BASE_DIR, {"seed": seed, "events": events})
    first_shown: dict[str, date] = {}
    before: dict[str, set] = {}         # findings already shown when the disruption began do not count as finding it
    day = f.base_date
    while day < BASE + timedelta(days=HORIZON):
        if mornings and day <= BASE + timedelta(days=WINDOW) and is_working(day) and day > BASE:
            b = briefing.build_rows(_orders(f), _log(f), day)
            for ev in events:
                start = date.fromisoformat(ev["start"])
                if day <= start:
                    before[ev["id"]] = _matching(ev, b["findings"], f)
                elif ev["id"] not in first_shown and _matching(ev, b["findings"], f) - before.get(ev["id"], set()):
                    first_shown[ev["id"]] = day
        f.step(day)
        day += timedelta(days=1)
    return {o["order_id"]: o for o in f.orders}, first_shown


def _orders(f: Factory) -> list[dict]:
    return [{**o, "pieces": int(o["pieces"]), "_file": "orders.csv", "_row": i + 2} for i, o in enumerate(f.orders)]


def _log(f: Factory) -> list[dict]:
    return [{**r, "pieces_completed": int(r["pieces_completed"]), "_file": "production_log.csv", "_row": i + 2} for i, r in enumerate(f.log)]


def _matching(ev: dict, findings: list[dict], f: Factory) -> set[str]:
    """The findings on the page that point at this disruption (as 'key' or 'key/order')."""
    keys = {x["key"] for x in findings}
    named = {f"quiet/{i}" for x in findings if x["type"] in ("quiet_order", "quiet_orders") for i in x["order_ids"]}
    if ev["type"] == "stage_slowdown":
        return keys & {f"stage_below:{ev['stage']}"}
    if ev["type"] == "customer_hold":
        mine = {f"quiet/{o['order_id']}" for o in f.orders if o["customer"] == ev["customer"]}
        return (keys & {f"customer_stalled:{ev['customer']}"}) | (mine & named)
    order = next(o for o in f.orders if o["order_id"] == ev["order_id"])
    return (named & {f"quiet/{ev['order_id']}"}) | (keys & {f"customer_stalled:{order['customer']}"})


def cut(events: list[dict], noticed: dict[str, date], response: int) -> list[dict]:
    """Each disruption ends `response` working days after it was noticed, if that is before it would have ended anyway."""
    out = []
    for ev in events:
        e = dict(ev)
        if ev["id"] in noticed:
            stop = add_working_days(noticed[ev["id"]], response) - timedelta(days=1)
            if stop < date.fromisoformat(ev["end"]):
                e["end"] = max(stop, date.fromisoformat(ev["start"]) - timedelta(days=1)).isoformat()
        out.append(e)
    return out


def hit_orders(events: list[dict], final: dict[str, dict]) -> set[str]:
    """Orders a hold stopped directly: the held order, or every order of the held customer."""
    custs = {e["customer"] for e in events if e["type"] == "customer_hold"}
    return {oid for oid, o in final.items() if o["customer"] in custs} | {e["order_id"] for e in events if e["type"] == "order_hold"}


def lateness(final: dict[str, dict], scored: set[str]) -> tuple[int, int]:
    total, late = 0, 0
    for oid in scored:
        o = final[oid]
        if not o["completed_date"]:
            raise RuntimeError(f"{oid} did not finish within the horizon; raise HORIZON")
        d = working_days_between(date.fromisoformat(o["due_date"]), date.fromisoformat(o["completed_date"]))
        total += max(0, d)
        late += d > 0
    return total, late


def one(seed: int) -> dict:
    events = plant(seed)
    base_final, shown = run(seed, events, mornings=True)
    scored = {oid for oid, o in base_final.items()
              if o["status"] != "COMPLETE" or not o["completed_date"] or o["completed_date"] >= BASE.isoformat()}
    scored = {oid for oid in scored if base_final[oid]["order_date"] < (BASE + timedelta(days=WINDOW)).isoformat()}
    manual = {lag: {ev["id"]: add_working_days(date.fromisoformat(ev["start"]), lag) for ev in events} for lag in SENSITIVITY["manual"]}
    out = {"seed": seed, "events": events, "shown": {k: v.isoformat() for k, v in shown.items()}, "scored": len(scored),
           "delay_copilot": {ev["id"]: working_days_between(date.fromisoformat(ev["start"]), shown[ev["id"]]) for ev in events if ev["id"] in shown},
           "nobody": lateness(base_final, scored), "arms": {}}
    hit = hit_orders(events, base_final) & scored
    for response in SENSITIVITY["response"]:
        for lag in SENSITIVITY["manual"]:
            noticed_hand = manual[lag]
            noticed_cp = {k: min(v, noticed_hand[k]) if k in noticed_hand else v for k, v in shown.items()}
            noticed_cp.update({k: v for k, v in noticed_hand.items() if k not in noticed_cp})
            hand, _ = run(seed, cut(events, noticed_hand, response))
            cp, _ = run(seed, cut(events, noticed_cp, response))
            out["arms"][f"m{lag}_r{response}"] = {"by_hand": lateness(hand, scored), "copilot": lateness(cp, scored),
                                                  "hit_by_hand": lateness(hand, hit), "hit_copilot": lateness(cp, hit)}
    return out


# ---------------------------------------------------------------- summary
def study() -> dict:
    runs = [one(seed) for seed in range(1, RUNS + 1)]
    kinds = {"customer_hold": "C", "order_hold": "O", "stage_slowdown": "S"}
    detect = {}
    for kind, prefix in kinds.items():
        n = sum(1 for r in runs for e in r["events"] if e["type"] == kind)
        found = [d for r in runs for k, d in r["delay_copilot"].items() if k.startswith(prefix)]
        detect[kind] = {"events": n, "shown": len(found), "pct": round(100 * len(found) / n, 1),
                        "median_delay": st.median(found) if found else None}
    grid = {}
    for key in runs[0]["arms"]:
        diff = [r["arms"][key]["by_hand"][0] - r["arms"][key]["copilot"][0] for r in runs]
        rel = [100 * d / r["arms"][key]["by_hand"][0] for d, r in zip(diff, runs) if r["arms"][key]["by_hand"][0]]
        late_diff = [r["arms"][key]["by_hand"][1] - r["arms"][key]["copilot"][1] for r in runs]
        m, s = st.mean(diff), st.stdev(diff)
        grid[key] = {"mean_days_avoided": round(m, 1), "ci95": [round(m - 1.96 * s / math.sqrt(len(diff)), 1), round(m + 1.96 * s / math.sqrt(len(diff)), 1)],
                     "median_pct": round(st.median(rel), 1), "runs_better": sum(d > 0 for d in diff), "runs_worse": sum(d < 0 for d in diff),
                     "late_orders_avoided": round(st.mean(late_diff), 2),
                     "mean_by_hand": round(st.mean(r["arms"][key]["by_hand"][0] for r in runs), 1),
                     "mean_copilot": round(st.mean(r["arms"][key]["copilot"][0] for r in runs), 1)}
    nobody = round(st.mean(r["nobody"][0] for r in runs), 1)
    key = f"m{MANUAL_LAG}_r{RESPONSE_LAG}"
    hd = [r["arms"][key]["hit_by_hand"][0] - r["arms"][key]["hit_copilot"][0] for r in runs]
    hit = {"mean_days_avoided": round(st.mean(hd), 1), "runs_better": sum(d > 0 for d in hd), "runs_worse": sum(d < 0 for d in hd),
           "mean_by_hand": round(st.mean(r["arms"][key]["hit_by_hand"][0] for r in runs), 1),
           "mean_copilot": round(st.mean(r["arms"][key]["hit_copilot"][0] for r in runs), 1)}
    return {"runs": RUNS, "scored_orders_mean": round(st.mean(r["scored"] for r in runs), 1), "nobody_mean": nobody,
            "detection": detect, "grid": grid, "hit": hit, "per_run": runs}


START, END = "<!-- value:start (generated by analysis/business_value.py from analysis/results/business_value.json) -->", "<!-- value:end -->"
KIND = {"customer_hold": "A customer's orders all stop", "order_hold": "One order stops", "stage_slowdown": "A stage slows down"}


def markdown(r: dict) -> str:
    main = r["grid"][f"m{MANUAL_LAG}_r{RESPONSE_LAG}"]
    out = ["### Did the briefing show each disruption, and how fast?\n",
           f"{r['runs']} simulated futures, 6 planted disruptions each. \"Shown\" = in the briefing's top five findings on some morning while it lasted.\n",
           "| Disruption | Planted | Shown by the briefing | Median working days from start to first shown |", "|---|---|---|---|"]
    for k, x in r["detection"].items():
        out.append(f"| {KIND[k]} | {x['events']} | {x['shown']} ({x['pct']:g}%) | {x['median_delay']:g} |")
    out += ["", f"### Lateness, with the main assumptions (noticed by hand after {MANUAL_LAG} working days; fixed {RESPONSE_LAG} working days after noticing)\n",
            f"Orders scored per future: {r['scored_orders_mean']:g} on average (everything in progress or arriving in the first {WINDOW} days, followed until it finished).\n",
            "| Version of the same future | Working days late, summed over orders (mean per future) |", "|---|---|",
            f"| Nobody acts | {r['nobody_mean']:,.1f} |", f"| Found by hand | {main['mean_by_hand']:,.1f} |", f"| Found by the co-pilot | {main['mean_copilot']:,.1f} |",
            "", f"Co-pilot against by hand: **{main['mean_days_avoided']:g} working days of lateness avoided per future** (95% interval {main['ci95'][0]:g} to "
                f"{main['ci95'][1]:g}; median {main['median_pct']:g}% less), {main['late_orders_avoided']:g} fewer late orders; better in {main['runs_better']} of "
                f"{r['runs']} futures, worse in {main['runs_worse']}.\n",
            f"Orders the holds stopped directly (the held orders, and every order of a held customer): {r['hit']['mean_by_hand']:g} working days late by hand, "
            f"{r['hit']['mean_copilot']:g} with the co-pilot; better in {r['hit']['runs_better']} of {r['runs']} futures, worse in {r['hit']['runs_worse']}.\n",
            "### How the result moves with the assumptions\n",
            "Working days of lateness avoided per future, co-pilot against by hand (mean, 95% interval):\n",
            "| Fixed this many working days after noticing | " + " | ".join(f"Noticed by hand after {m}" for m in SENSITIVITY["manual"]) + " |",
            "|---|" + "---|" * len(SENSITIVITY["manual"])]
    for resp in SENSITIVITY["response"]:
        cells = []
        for m in SENSITIVITY["manual"]:
            g = r["grid"][f"m{m}_r{resp}"]
            cells.append(f"{g['mean_days_avoided']:g} ({g['ci95'][0]:g} to {g['ci95'][1]:g})")
        out.append(f"| {resp} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def render_doc(r: dict) -> str:
    text = DOC.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n\n{markdown(r)}\n{END}{tail}"


def main() -> None:
    if "--render" not in sys.argv:
        r = study()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(r, indent=1, default=str) + "\n", encoding="utf-8")
    r = json.loads(OUT.read_text(encoding="utf-8"))
    if DOC.exists():
        DOC.write_text(render_doc(r), encoding="utf-8")
    print(markdown(r))


if __name__ == "__main__":
    main()
