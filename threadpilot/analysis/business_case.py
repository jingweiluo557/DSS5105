"""What ThreadPilot is worth in hours and money: a costed business case.

Two sources of value, kept apart because one is measured in simulation and the other is estimated:

1. Labour. The work a planner does today to answer the general manager: the morning report (the course brief's "half hour
   every morning") and each "let me check and call you back". Minutes per task are estimates (low, likely, high), drawn
   10,000 times; the output is a range, not one number.
2. Lateness. The paired simulation in docs/business_value.md: finding problems through the briefing avoided about 30.5
   working days of lateness per two months. Here it is priced with a late-delivery penalty from a real retailer's vendor
   terms, applied at half that retailer's rate, on order values from assumed selling prices (the data has none).

Every input is in INPUTS below with its source or the word "assumption". Change one and re-run:
    python -m analysis.business_case            # writes analysis/results/business_case.json and the tables in
                                                #   docs/business_case.md
"""
import csv
import json
import random
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "analysis" / "results" / "business_case.json"
DOC = ROOT / "docs" / "business_case.md"

INPUTS = {
    # ---- calendar
    "factory_days_per_month": 26,          # data: the factory works Monday to Saturday, closed Sundays
    "paid_hours_per_month": 190.7,         # Singapore standard 44-hour week x 52 / 12
    # ---- people (SGD)
    "planner_base_salary_year": 48171,     # Payscale, Production Planner (Manufacturing), Singapore, average base
    "employer_cpf_rate": 0.17,             # employer CPF contribution for a Singapore citizen or PR under 55
    "assistant_base_salary_month": 3500,   # assumption: a junior planning assistant, about the low end of the planner range
    # ---- running ThreadPilot
    "usd_to_sgd": 1.30,                    # assumption: approximate rate; small effect on the result
    "cny_to_sgd": 0.18,                    # assumption: approximate rate
    "openai_usd_per_m_input": 2.00,        # GPT-4.1 price per million input tokens
    "openai_usd_per_m_output": 8.00,       # GPT-4.1 price per million output tokens
    "model_calls_per_question": 2,         # the live backend: understand the question, then word the answer
    "input_tokens_per_call": 4000,         # assumption: instructions, tool results and conversation so far
    "output_tokens_per_call": 600,         # assumption
    "questions_per_day": 25,               # assumption: generous; the brief's five questions plus follow-ups
    "cloudbase_cny_per_month": 199,        # CloudBase Standard plan (the Personal plan is 19.9)
    "maintenance_hours_per_month": 4,      # assumption: someone checks the system and data feed
    # ---- lateness (USD)
    "late_penalty_per_working_day": 0.01,  # assumption: half of URBN's 2% per day vendor late charge
    "late_penalty_cap": 0.10,              # URBN caps chargebacks at 10% of the order's FOB cost
    "fob_usd_per_piece": {                 # assumption: mid-market knitwear selling prices (FOB) per piece
        "Hoodie": 9, "Cardigan": 10, "Crewneck sweater": 9, "Vest": 7, "Polo shirt": 6, "Beanie": 3, "Scarf": 4,
    },
}

# Planner work that ThreadPilot replaces, per factory day. minutes = (low, likely, high); per_day = (low, likely, high).
# "With" = what is left for a person once ThreadPilot does the preparation (reading the briefing, acting on exceptions).
TASKS = [
    (("Morning report: export orders and production log, refresh the spreadsheet, compare each stage with its usual "
      "level, look for stalled orders, write the summary"), (20, 30, 60), (1, 1, 1), (3, 5, 10)),
    ("Order status call-back (“How is the TrendCart order doing?”)", (5, 10, 20), (2, 3, 5), (0, 1, 2)),
    ("Can we take this order? (capacity, queue, finish date)", (30, 45, 90), (0.2, 0.5, 1), (5, 10, 15)),
    ("Why did a stage drop? (pull history, chart, explain)", (15, 30, 60), (0.3, 0.5, 1), (2, 5, 10)),
    ("Chase-up: find the order and owner, draft and send", (5, 10, 15), (0.5, 1, 2), (1, 2, 3)),
    ("Reminder: re-check tomorrow whether a stage caught up", (5, 10, 15), (0.5, 1, 2), (0, 0, 1)),
    ("Weekly KPI dashboard and report (per factory day: weekly time / 6)", (10, 20, 30), (1, 1, 1), (2, 5, 8)),
]
DRAWS = 10_000


def tri(rng, low, mode, high):
    return rng.triangular(low, high, mode) if high > low else low


def labour(rng):
    """Planner minutes per factory day, without and with ThreadPilot, one draw."""
    before = after = 0.0
    for _, minutes, per_day, residual in TASKS:
        n = tri(rng, *per_day)
        before += n * tri(rng, *minutes)
        after += n * tri(rng, *residual)
    return before, after


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(p / 100 * len(values)))]


def order_value_usd():
    prices = INPUTS["fob_usd_per_piece"]
    with open(ROOT / "data" / "orders.csv", encoding="utf-8") as f:
        orders = list(csv.DictReader(f))
    values = [int(o["pieces"]) * prices[o["product"]] for o in orders]
    return st.mean(values), len(orders)


def main():
    rng = random.Random(5105)
    i = INPUTS
    days, hours = i["factory_days_per_month"], i["paid_hours_per_month"]
    planner_month = i["planner_base_salary_year"] / 12 * (1 + i["employer_cpf_rate"])
    rate = planner_month / hours
    assistant_month = i["assistant_base_salary_month"] * (1 + i["employer_cpf_rate"])

    draws = [labour(rng) for _ in range(DRAWS)]
    saved_h = [(b - a) * days / 60 for b, a in draws]
    before_h = [b * days / 60 for b, _ in draws]
    after_h = [a * days / 60 for _, a in draws]

    # running cost per month, SGD
    per_question = i["model_calls_per_question"] * (i["input_tokens_per_call"] * i["openai_usd_per_m_input"]
                                                    + i["output_tokens_per_call"] * i["openai_usd_per_m_output"]) / 1e6
    model_month = per_question * i["questions_per_day"] * days * i["usd_to_sgd"]
    cloud_month = i["cloudbase_cny_per_month"] * i["cny_to_sgd"]
    upkeep_month = i["maintenance_hours_per_month"] * rate
    running_month = model_month + cloud_month + upkeep_month

    # lateness, from the paired simulation (two simulated months per future)
    sim = json.loads((ROOT / "analysis" / "results" / "business_value.json").read_text())
    main_grid = sim["grid"]["m5_r2"]
    avg_order_usd, n_orders = order_value_usd()
    per_order_day_sgd = avg_order_usd * i["late_penalty_per_working_day"] * i["usd_to_sgd"]
    late = {k: round(v * per_order_day_sgd * 6, -2) for k, v in
            (("mean", main_grid["mean_days_avoided"]), ("low", main_grid["ci95"][0]), ("high", main_grid["ci95"][1]))}
    sensitivity = {key: round(g["mean_days_avoided"] * per_order_day_sgd * 6, -2) for key, g in sim["grid"].items()}

    labour_year = [h * rate * 12 for h in saved_h]
    total_mid = st.median(labour_year) + late["mean"] - running_month * 12
    out = {
        "inputs": INPUTS,
        "tasks": [{"task": t, "minutes": m, "per_day": f, "minutes_with_threadpilot": r} for t, m, f, r in TASKS],
        "planner_loaded_month_sgd": round(planner_month), "planner_rate_sgd_per_hour": round(rate, 1),
        "assistant_loaded_month_sgd": round(assistant_month),
        "hours_month_before": [round(pct(before_h, p)) for p in (10, 50, 90)],
        "hours_month_after": [round(pct(after_h, p)) for p in (10, 50, 90)],
        "hours_month_saved": [round(pct(saved_h, p)) for p in (10, 50, 90)],
        "fte_saved": [round(pct(saved_h, p) / hours, 2) for p in (10, 50, 90)],
        "labour_value_year_sgd": [round(pct(labour_year, p), -2) for p in (10, 50, 90)],
        "running_month_sgd": {"model": round(model_month), "cloud": round(cloud_month), "upkeep": round(upkeep_month),
                              "total": round(running_month)},
        "per_question_usd": round(per_question, 4),
        "avg_order_value_usd": round(avg_order_usd), "orders": n_orders,
        "late_value_per_order_day_sgd": round(per_order_day_sgd),
        "lateness": {"days_avoided_per_2_months": main_grid["mean_days_avoided"], "ci95": main_grid["ci95"],
                     "late_orders_avoided_per_2_months": main_grid["late_orders_avoided"],
                     "value_year_sgd": late, "sensitivity_year_sgd": sensitivity},
        "assistant_year_sgd": round(assistant_month * 12, -2),
        "running_year_sgd": round(running_month * 12, -2),
        "net_year_mid_sgd": round(total_mid, -2),
    }
    RESULTS.write_text(json.dumps(out, indent=2) + "\n")
    render(out)
    print(json.dumps({k: out[k] for k in ("hours_month_saved", "fte_saved", "labour_value_year_sgd", "running_month_sgd",
                                          "avg_order_value_usd", "late_value_per_order_day_sgd", "lateness",
                                          "assistant_year_sgd", "net_year_mid_sgd")}, indent=1))


def money(x):
    return f"S${x:,.0f}"


def tables(o):
    lo, mid, hi = o["hours_month_saved"]
    rows = ["| Task the planner does today | Minutes each (low / likely / high) | Times per factory day | Minutes each with ThreadPilot |",
            "|---|---|---|---|"]
    for t in o["tasks"]:
        m, f, r = t["minutes"], t["per_day"], t["minutes_with_threadpilot"]
        rows.append(f"| {t['task']} | {m[0]} / {m[1]} / {m[2]} | {f[0]:g} / {f[1]:g} / {f[2]:g} | {r[0]} / {r[1]} / {r[2]} |")
    lv, rm, la = o["labour_value_year_sgd"], o["running_month_sgd"], o["lateness"]
    sens = la["sensitivity_year_sgd"]
    out = "\n".join(rows) + f"""

### Hours

| | Low (10th percentile) | Likely (median) | High (90th percentile) |
|---|---|---|---|
| Planner hours a month on this work today | {o['hours_month_before'][0]} | {o['hours_month_before'][1]} | {o['hours_month_before'][2]} |
| Hours a month left with ThreadPilot | {o['hours_month_after'][0]} | {o['hours_month_after'][1]} | {o['hours_month_after'][2]} |
| **Hours a month saved** | **{lo}** | **{mid}** | **{hi}** |
| Share of one full-time planner | {o['fte_saved'][0]:.0%} | {o['fte_saved'][1]:.0%} | {o['fte_saved'][2]:.0%} |
| Value of that time a year (at {money(o['planner_rate_sgd_per_hour'])} an hour, salary + CPF) | {money(lv[0])} | {money(lv[1])} | {money(lv[2])} |

### Running ThreadPilot

| Item | Per month |
|---|---|
| OpenAI model ({o['inputs']['questions_per_day']} questions a day, about US${o['per_question_usd']:.3f} each) | {money(rm['model'])} |
| CloudBase Standard plan (¥{o['inputs']['cloudbase_cny_per_month']}) | {money(rm['cloud'])} |
| Upkeep ({o['inputs']['maintenance_hours_per_month']} hours of a planner's time) | {money(rm['upkeep'])} |
| **Total** | **{money(rm['total'])}** (about {money(o['running_year_sgd'])} a year) |

### Lateness avoided, priced

Average order: {o['orders']} orders in the data, about US${o['avg_order_value_usd']:,} each at the assumed prices. One working day
late on one order costs {money(o['late_value_per_order_day_sgd'])} at a 1% a day penalty.

| | Working days of lateness avoided per two months | Value a year |
|---|---|---|
| Main result (noticed by hand after 5 working days, fixed 2 days after noticing) | {la['days_avoided_per_2_months']} (95% interval {la['ci95'][0]} to {la['ci95'][1]}) | **{money(la['value_year_sgd']['mean'])}** ({money(la['value_year_sgd']['low'])} to {money(la['value_year_sgd']['high'])}) |
| If problems are noticed by hand within 3 working days | | {money(sens['m3_r2'])} |
| If they take 10 working days to notice | | {money(sens['m10_r2'])} |

### Together, a year (likely case)

| | A year |
|---|---|
| Planner time freed | {money(lv[1])} |
| Lateness penalties avoided | {money(la['value_year_sgd']['mean'])} |
| Minus running ThreadPilot | −{money(o['running_year_sgd'])} |
| **Net value** | **{money(o['net_year_mid_sgd'])}** |
| For comparison: hiring a full-time planning assistant to give the same on-call answers | {money(o['assistant_year_sgd'])} |"""
    return out


def render(o):
    text = DOC.read_text(encoding="utf-8")
    start, end = "<!-- case:start (generated by analysis/business_case.py) -->", "<!-- case:end -->"
    a, b = text.index(start) + len(start), text.index(end)
    DOC.write_text(text[:a] + "\n\n" + tables(o) + "\n\n" + text[b:], encoding="utf-8")


if __name__ == "__main__":
    main()
