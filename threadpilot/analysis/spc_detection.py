"""Which rule should decide that a stage's output is abnormal? A Monte Carlo detection study with known truth.

The briefing calls a stage "below normal" when yesterday's output is under mean - max(1.5 SD, 5% of mean) of the previous
8 same weekdays. That rule was chosen by reasoning, not measured. This study measures it against standard statistical
process control (SPC) rules, all built on the SAME baseline (previous 8 same weekdays, Sundays closed):

    current      x < mean - max(1.5 SD, 5% mean)               (the product's rule today)
    shewhart_3s  x < mean - 3 SD                                (Shewhart individuals chart, 3-sigma lower limit)
    we_rules     Western Electric rules on z = (x - mean) / SD:  1 point < -3, or 2 of 3 < -2, or 4 of 5 < -1, or 8 in a row < 0
    ewma         EWMA of z, lambda = 0.2, alarm below -3 sqrt(lambda / (2 - lambda))   (L = 3)
    cusum        lower CUSUM of z, k = 0.5, h = 4
    3s_cusum     shewhart_3s OR cusum, computed by the SHIPPED code (simulation.briefing.stage_alarm), so the row that decides
                 the product is the product, not a re-implementation

Only drops count (an alarm on the low side): a stage running high is not something to interrupt a manager about.

How the truth is made. Each stage's in-control output is generated from the REAL production log: the weekday means of the
provided 90 days, times residuals resampled from that log in blocks of one working week (so real tails and week-to-week
correlation are kept). The one real event in the log, assembly's fall of about 45% from 25 March, is left out of the
residual pool and used instead as a real test case. Then a drop of known size and length is planted. A day with a planted
drop is abnormal; every other day is in control, and an alarm on it is a false alarm. Eight weeks of warm-up fill the
baseline before anything is judged.

    python -m analysis.spc_detection            # a few seconds; writes analysis/results/spc_detection.json

Limits: queues never run dry here (the real factory is overloaded, so this is the realistic case, but a stage that runs out
of work also shows a drop, which the briefing reports separately as "may be short of work"). Resampling assumes the 90 days
are typical of the factory.
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics as st
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from simulation import briefing

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "production_log.csv"
OUT = ROOT / "analysis" / "results" / "spc_detection.json"
STAGES = ["KNITTING", "ASSEMBLY", "WASHING", "PACKING"]
REAL_EVENT = ("ASSEMBLY", date(2026, 3, 25))   # assembly falls from about 770 to about 420 pieces a day and stays there
WARMUP_WEEKS, EVAL_WEEKS = 8, 8
BASELINE_WEEKS, MIN_SAMPLES = 8, 3
METHODS = ["current", "shewhart_3s", "we_rules", "ewma", "cusum", "3s_cusum"]
EWMA_LAMBDA, EWMA_L = 0.2, 3.0
CUSUM_K, CUSUM_H = 0.5, 4.0
MAGNITUDES = [0.5, 0.7, 0.8, 0.9]  # planted output factor: 0.9 = a 10% drop
DURATIONS = [1, 3, 8]              # working days
DETECT_WINDOW = 5                  # an alarm up to 5 working days after the drop ends still counts as detecting it
MONDAY = date(2030, 1, 7)          # a synthetic calendar: only the weekday pattern matters


# ---------------------------------------------------------------- the in-control process, from the real log
def read_log() -> dict[tuple[str, date], int]:
    with LOG.open(newline="", encoding="utf-8") as fh:
        return {(r["stage"], date.fromisoformat(r["date"])): int(r["pieces_completed"]) for r in csv.DictReader(fh)}


def calibrate(log: dict) -> dict:
    """Per stage: the mean output for each weekday, and the residual (x / weekday mean - 1) of every working day, in date order."""
    model = {}
    for s in STAGES:
        days = sorted(d for st_, d in log if st_ == s and d.weekday() != 6 and not (s == REAL_EVENT[0] and d >= REAL_EVENT[1]))
        means = {w: st.mean(log[(s, d)] for d in days if d.weekday() == w) for w in range(6)}
        model[s] = {"means": means, "residuals": [log[(s, d)] / means[d.weekday()] - 1 for d in days]}
    return model


def workdays(n: int) -> list[date]:
    out, day = [], MONDAY
    while len(out) < n:
        if day.weekday() != 6:
            out.append(day)
        day += timedelta(days=1)
    return out


def series(model: dict, stage: str, rng: random.Random, factors: dict[int, float] | None = None) -> tuple[dict, list[date]]:
    """Warm-up plus evaluation weeks of in-control output, with planted factors on the given working-day indexes."""
    days = workdays(6 * (WARMUP_WEEKS + EVAL_WEEKS))
    res, m = model[stage]["residuals"], model[stage]["means"]
    draws: list[float] = []
    while len(draws) < len(days):                      # block bootstrap: one working week at a time
        i = rng.randrange(0, len(res) - 6)
        draws.extend(res[i:i + 6])
    factors = factors or {}
    out = {(stage, d): max(0, round(m[d.weekday()] * (1 + draws[i]) * factors.get(i, 1.0))) for i, d in enumerate(days)}
    return out, days


# ---------------------------------------------------------------- the rules
def baseline(output: dict, stage: str, day: date) -> list[int]:
    samples, probe = [], day - timedelta(days=7)
    first = min(d for s, d in output if s == stage)
    while len(samples) < BASELINE_WEEKS and probe >= first:
        if (stage, probe) in output:
            samples.append(output[(stage, probe)])
        probe -= timedelta(days=7)
    return samples


def alarms(output: dict, stage: str, days: list[date]) -> dict[str, set[date]]:
    """The days each method raises an alarm for one stage, in date order (rules with memory run across working days)."""
    out = {m: set() for m in METHODS}
    zs: list[float] = []
    ewma, cusum = 0.0, 0.0
    ewma_limit = -EWMA_L * math.sqrt(EWMA_LAMBDA / (2 - EWMA_LAMBDA))
    for day in days:
        b = baseline(output, stage, day)
        if len(b) < MIN_SAMPLES:
            continue
        m, sd, x = st.mean(b), st.pstdev(b), output[(stage, day)]
        sd = max(sd, 1e-9)
        z = (x - m) / sd
        zs.append(z)
        if x < m - max(1.5 * sd, 0.05 * m):
            out["current"].add(day)
        if z < -3:
            out["shewhart_3s"].add(day)
        last = zs[-8:]
        if (z < -3 or sum(v < -2 for v in last[-3:]) >= 2 or sum(v < -1 for v in last[-5:]) >= 4
                or (len(last) == 8 and all(v < 0 for v in last))):
            out["we_rules"].add(day)
        ewma = EWMA_LAMBDA * z + (1 - EWMA_LAMBDA) * ewma
        if ewma < ewma_limit:
            out["ewma"].add(day)
            ewma = 0.0
        cusum = min(0.0, cusum + z + CUSUM_K)
        if cusum < -CUSUM_H:
            out["cusum"].add(day)
            cusum = 0.0
    log_by_stage = {stage: {d: {"date": d.isoformat(), "stage": stage, "pieces_completed": v, "_file": "x", "_row": 0}
                            for (s_, d), v in output.items() if s_ == stage}}
    out["3s_cusum"] = {d for d in days if len(baseline(output, stage, d)) >= MIN_SAMPLES
                       and briefing.stage_alarm(log_by_stage, stage, d)["alarm"]}
    return out


# ---------------------------------------------------------------- the study
def false_alarms(model: dict, runs: int = 400) -> dict:
    counts = {m: 0 for m in METHODS}
    days_judged = 0
    for s in STAGES:
        for k in range(runs):
            out, days = series(model, s, random.Random(f"null|{s}|{k}"))
            fired = alarms(out, s, days)
            judged = days[6 * WARMUP_WEEKS:]
            days_judged += len(judged)
            for m in METHODS:
                counts[m] += sum(d in fired[m] for d in judged)
    month = 26 * len(STAGES)          # stage-days in a working month for the whole factory
    return {"in_control_stage_days": days_judged, "false_alarms": counts,
            "per_100_stage_days": {m: round(100 * c / days_judged, 2) for m, c in counts.items()},
            "per_month_factory": {m: round(month * c / days_judged, 1) for m, c in counts.items()}}


def detection(model: dict, runs: int = 200) -> dict:
    """One planted drop per run, on a random stage and start day in the evaluation weeks. Detected = an alarm at that stage
    from the drop's first day to DETECT_WINDOW working days after its last; delay in working days (0 = flagged on day one)."""
    table = []
    first = 6 * WARMUP_WEEKS
    for factor in MAGNITUDES:
        for duration in DURATIONS:
            delays = {m: [] for m in METHODS}
            for k in range(runs):
                rng = random.Random(f"event|{factor}|{duration}|{k}")
                stage = rng.choice(STAGES)
                start = rng.randrange(first + 6, first + 6 * EVAL_WEEKS - duration - DETECT_WINDOW)
                out, days = series(model, stage, rng, {i: factor for i in range(start, start + duration)})
                fired = alarms(out, stage, days)
                window = days[start:start + duration + DETECT_WINDOW]
                for m in METHODS:
                    delays[m].append(next((i for i, d in enumerate(window) if d in fired[m]), None))
            entry = {"drop_pct": round(100 * (1 - factor)), "duration_workdays": duration, "runs": runs}
            for m, ds in delays.items():
                hits = [d for d in ds if d is not None]
                entry[m] = {"detected_pct": round(100 * len(hits) / runs), "mean_delay_workdays": round(st.mean(hits), 2) if hits else None}
            table.append(entry)
    return {"events": table}


def real_data(log: dict) -> dict:
    """The rules on the provided 90-day log. No ground truth except the assembly drop from 25 March, which every rule should catch."""
    days = sorted({d for _, d in log if d.weekday() != 6})
    fired = {s: alarms(log, s, days) for s in STAGES}
    stage, start = REAL_EVENT
    event_days = [d for d in days if d >= start]
    before = [d for d in days if d < start]
    return {"first_day": days[0].isoformat(), "last_day": days[-1].isoformat(),
            "judged_stage_days": sum(len(baseline(log, s, d)) >= MIN_SAMPLES for s in STAGES for d in days),
            "alarms_before_the_event": {m: sum(len([d for d in fired[s][m] if d in before]) for s in STAGES) for m in METHODS},
            "assembly_event_days_flagged": {m: f"{sum(d in fired[stage][m] for d in event_days)} of {len(event_days)}" for m in METHODS},
            "assembly_event_first_flag": {m: next((d.isoformat() for d in event_days if d in fired[stage][m]), None) for m in METHODS}}


def study() -> dict:
    log = read_log()
    model = calibrate(log)
    return {"settings": {"warmup_weeks": WARMUP_WEEKS, "eval_weeks": EVAL_WEEKS, "baseline_weeks": BASELINE_WEEKS,
                         "ewma": {"lambda": EWMA_LAMBDA, "L": EWMA_L}, "cusum": {"k": CUSUM_K, "h": CUSUM_H},
                         "detect_window_workdays": DETECT_WINDOW,
                         "noise_sd_pct": {s: round(100 * st.pstdev(model[s]["residuals"]), 1) for s in STAGES}},
            "false_alarms": false_alarms(model), "detection": detection(model), "real_data": real_data(log)}


LABEL = {"current": "Current band (1.5 SD, 5% floor)", "shewhart_3s": "Shewhart 3-sigma", "we_rules": "Western Electric rules",
         "ewma": "EWMA (0.2, 3-sigma)", "cusum": "CUSUM (k 0.5, h 4)", "3s_cusum": "3-sigma + CUSUM (shipped)"}


def markdown(r: dict) -> str:
    fa, det, real = r["false_alarms"], r["detection"]["events"], r["real_data"]
    lines = ["### False alarms (no drop planted)\n",
             f"{fa['in_control_stage_days']:,} in-control stage-days, with noise resampled from the real log "
             f"(day-to-day spread: " + ", ".join(f"{s.title()} {v}%" for s, v in r["settings"]["noise_sd_pct"].items()) + ").\n",
             "| Rule | False alarms per 100 stage-days | False alarms per month, whole factory | Alarms on the real log before 25 March |",
             "|---|---|---|---|"]
    for m in METHODS:
        lines.append(f"| {LABEL[m]} | {fa['per_100_stage_days'][m]} | {fa['per_month_factory'][m]} | {real['alarms_before_the_event'][m]} |")
    lines += ["", f"A month is 26 working days x 4 stages. The real log ({real['first_day']} to {real['last_day']}, "
              f"{real['judged_stage_days']} judged stage-days) has no ground truth before 25 March, so that column is alert volume, not accuracy.", "",
              "### Detection of planted drops (detected % / mean delay in working days, 0 = flagged on the first day)\n",
              "| Drop | Lasts | " + " | ".join(LABEL[m] for m in METHODS) + " |",
              "|---|---|" + "---|" * len(METHODS)]
    for e in det:
        cells = []
        for m in METHODS:
            v = e[m]
            cells.append(f"{v['detected_pct']}%" + (f" / {v['mean_delay_workdays']}" if v["mean_delay_workdays"] is not None else ""))
        lines.append(f"| {e['drop_pct']}% | {e['duration_workdays']} d | " + " | ".join(cells) + " |")
    lines += ["", f"{det[0]['runs']} runs per row, the stage and start day drawn at random. The briefing reads yesterday's data, "
              "so the manager hears about a drop one morning after the day it is flagged.", "",
              "### The real event: assembly from 25 March\n",
              "| Rule | Event days flagged | First flagged |", "|---|---|---|"]
    for m in METHODS:
        lines.append(f"| {LABEL[m]} | {real['assembly_event_days_flagged'][m]} | {real['assembly_event_first_flag'][m] or 'never'} |")
    return "\n".join(lines) + "\n"


DOC = ROOT / "docs" / "spc_detection.md"
SVG = ROOT / "docs" / "images" / "spc_tradeoff.svg"
START, END = "<!-- spc:start (generated by analysis/spc_detection.py from analysis/results/spc_detection.json) -->", "<!-- spc:end -->"


def svg(r: dict) -> str:
    """False alarms per month (x) against detection of a 20% drop lasting 3 days (y): up and to the left is better."""
    fa = r["false_alarms"]["per_month_factory"]
    cell = next(e for e in r["detection"]["events"] if e["drop_pct"] == 20 and e["duration_workdays"] == 3)
    W, H, L, B, T, R = 720, 420, 70, 60, 40, 30
    xmax, ymin = 14, 50
    X = lambda v: L + (W - L - R) * v / xmax
    Y = lambda v: T + (H - T - B) * (1 - (v - ymin) / (100 - ymin))
    ink, muted, grid = "#16262B", "#5E6E7A", "#D5DEE0"
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" font-family="Calibri, Arial, sans-serif">',
             "<title>False alarms per month against detection of a 20% drop lasting 3 days, for six rules</title>",
             f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    for v in range(ymin, 101, 10):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{grid}" stroke-width="1"/>')
        parts.append(f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" font-size="12" fill="{muted}">{v}%</text>')
    for v in range(0, xmax + 1, 2):
        parts.append(f'<text x="{X(v):.1f}" y="{H - B + 18}" text-anchor="middle" font-size="12" fill="{muted}">{v}</text>')
    parts.append(f'<text x="{(L + W - R) / 2}" y="{H - 14}" text-anchor="middle" font-size="13" fill="{ink}">False alarms per month, whole factory (fewer is better)</text>')
    parts.append(f'<text x="18" y="{(T + H - B) / 2}" text-anchor="middle" font-size="13" fill="{ink}" transform="rotate(-90 18 {(T + H - B) / 2})">20% drop for 3 days: detected</text>')
    offsets = {"current": (-8, -12, "end"), "shewhart_3s": (10, 16, "start"), "we_rules": (10, 4, "start"), "ewma": (10, 4, "start"),
               "cusum": (-4, 22, "middle"), "3s_cusum": (12, -12, "start")}
    for m in METHODS:
        x, y = X(fa[m]), Y(cell[m]["detected_pct"])
        shipped = m == "3s_cusum"
        colour = "#D9532B" if shipped else "#2E6F77"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{7 if shipped else 5}" fill="{colour}" stroke="#FFFFFF" stroke-width="2">'
                     f'<title>{LABEL[m]}: {fa[m]} false alarms a month, {cell[m]["detected_pct"]}% detected</title></circle>')
        dx, dy, anchor = offsets[m]
        weight = ' font-weight="bold"' if shipped else ""
        parts.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" text-anchor="{anchor}" font-size="12" fill="{ink}"{weight}>{LABEL[m]}</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_doc(r: dict) -> str:
    text = DOC.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n\n{markdown(r)}\n{END}{tail}"


def main() -> None:
    import sys
    if "--render" not in sys.argv:        # the full study takes about six minutes; --render only redraws from the saved results
        r = study()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8")
    r = json.loads(OUT.read_text(encoding="utf-8"))
    DOC.write_text(render_doc(r), encoding="utf-8")
    SVG.write_text(svg(r), encoding="utf-8")
    print(markdown(r))


if __name__ == "__main__":
    main()
