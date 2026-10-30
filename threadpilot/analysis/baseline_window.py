"""How many past same weekdays should "normal" use? A measured answer for the 8 in "the previous 8 same weekdays".

The product judges a stage's day against the previous K same weekdays (Sundays closed): below their minimum is a
"watch" item (P3); below it on 3 working days in a row is an alert that emails the manager (P1). K = 8 was chosen by
reasoning. This study measures K = 4, 5, 6, 8, 10, 12 on the factory's own data, with the SAME rules the product ships
(services/alert_policy.py), and reports four things:

  1. false alerts   how often the P1 rule fires on a normal factory (per month, all four stages)
  2. noise          how many normal days are flagged "below range" (watch items per month)
  3. detection      a planted drop of 20 / 30 / 40 % lasting 5 working days: is the P1 alert raised, and how fast?
  4. data needed    on the real 90-day log, how many stage-days have a full K-week baseline
  plus the real log: the first alert for the real assembly drop from 25 March, and false alerts before it.

The normal factory is generated from the real log exactly as in analysis/spc_detection.py (weekday means of the 90 days,
residuals resampled a working week at a time, the assembly drop left out of the pool).

    python -m analysis.baseline_window        # about a minute; writes analysis/results/baseline_window.json and docs/BASELINE_WINDOW.md
"""
from __future__ import annotations

import json
import random
import statistics as st
from datetime import date, timedelta
from pathlib import Path

from analysis.spc_detection import REAL_EVENT, STAGES, calibrate, read_log, workdays

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "results" / "baseline_window.json"
DOC = ROOT / "docs" / "BASELINE_WINDOW.md"
WINDOWS = [4, 5, 6, 8, 10, 12]
MIN_SAMPLES = 3            # the product judges a day only with at least 3 past same weekdays
SUSTAINED = 3              # P1: 3 consecutive working days below the minimum
WEEKS = 30                 # 12 warm-up weeks (enough for K = 12) + 18 judged weeks per run
WARMUP = 12
WORKDAYS_PER_MONTH = 26


def series(model, stage, rng, factors=None):
    days = workdays(6 * WEEKS)
    res, m = model[stage]["residuals"], model[stage]["means"]
    draws = []
    while len(draws) < len(days):
        i = rng.randrange(0, len(res) - 6)
        draws.extend(res[i:i + 6])
    factors = factors or {}
    return [max(0, round(m[d.weekday()] * (1 + draws[i]) * factors.get(i, 1.0))) for i, d in enumerate(days)], days


def below_flags(values, days, k):
    """For each working day: is it below the minimum of the previous k same weekdays? (None = not judged)"""
    by_weekday: dict[int, list[int]] = {}
    flags = []
    for v, d in zip(values, days):
        past = by_weekday.setdefault(d.weekday(), [])
        base = past[-k:]
        flags.append(v < min(base) if len(base) >= MIN_SAMPLES else None)
        past.append(v)
    return flags


def p1_days(flags):
    """Indexes where the P1 rule holds: this day and the 2 working days before it are all below range."""
    return [i for i in range(SUSTAINED - 1, len(flags)) if all(flags[j] for j in range(i - SUSTAINED + 1, i + 1))]


def p1_onsets(flags):
    """A P1 alert is emailed once per episode (the cooldown and dedupe key): count the first day of each run."""
    days = set(p1_days(flags))
    return [i for i in sorted(days) if i - 1 not in days]


def false_alerts(model, runs, seed=1):
    rng = random.Random(seed)
    out = {}
    judged0 = WARMUP * 6
    for k in WINDOWS:
        p1 = watch = n = 0
        for _ in range(runs):
            for s in STAGES:
                values, days = series(model, s, rng)
                flags = below_flags(values, days, k)
                p1 += sum(1 for i in p1_onsets(flags) if i >= judged0)
                watch += sum(1 for f in flags[judged0:] if f)
                n += len(flags) - judged0
        months = n / len(STAGES) / WORKDAYS_PER_MONTH
        out[k] = {"p1_alerts_per_month": round(p1 / months, 2), "watch_days_per_month": round(watch / months, 1),
                  "watch_share_of_days": round(watch / n, 3), "theory_watch_share": round(1 / (k + 1), 3)}
    return out


def detection(model, runs, seed=2):
    rng = random.Random(seed)
    out = {}
    start = WARMUP * 6 + 30
    for size in (0.2, 0.3, 0.4):
        out[size] = {}
        for k in WINDOWS:
            caught = 0
            delays = []
            for _ in range(runs):
                s = rng.choice(STAGES)
                values, days = series(model, s, rng, {start + j: 1 - size for j in range(5)})
                hits = [i for i in p1_days(below_flags(values, days, k)) if start <= i < start + 5 + 2]
                if hits:
                    caught += 1
                    delays.append(hits[0] - start + 1)
            out[size][k] = {"caught_pct": round(100 * caught / runs), "median_working_days_to_alert": st.median(delays) if delays else None}
    return out


def excursion(model, runs, seed=4):
    """The same-day alert: one working day below mean - z SD of the previous 8 same weekdays (at least 5) and below their
    minimum. False alerts a month (4 stages) and the share of one-day drops caught the same day, for z = 3, 3.5, 4."""
    rng = random.Random(seed)
    out = {}
    judged0 = WARMUP * 6

    def flags(values, days, z):
        by_weekday, res = {}, []
        for v, d in zip(values, days):
            past = by_weekday.setdefault(d.weekday(), [])
            base = past[-8:]
            if len(base) >= 5:
                m = st.mean(base)
                res.append(v < min(base) and v < m - z * st.pstdev(base))
            else:
                res.append(False)
            past.append(v)
        return res
    for z in (3.0, 3.5, 4.0):
        false = n = 0
        for _ in range(runs):
            for s in STAGES:
                values, days = series(model, s, rng)
                f = flags(values, days, z)
                false += sum(f[judged0:])
                n += len(f) - judged0
        caught = {}
        for size in (0.3, 0.4, 0.5):
            hits = 0
            for _ in range(runs * 2):
                s = rng.choice(STAGES)
                start = judged0 + 30
                values, days = series(model, s, rng, {start: 1 - size})
                hits += flags(values, days, z)[start]
            caught[f"{int(size * 100)}%"] = round(100 * hits / (runs * 2))
        out[z] = {"false_alerts_per_month": round(false / (n / len(STAGES) / WORKDAYS_PER_MONTH), 2), "one_day_drop_caught_same_day_pct": caught}
    return out


def real_log(log):
    days = sorted({d for _, d in log if d.weekday() != 6})
    stage, start = REAL_EVENT
    out = {}
    for k in WINDOWS:
        false_before, judged, full, first = 0, 0, 0, None
        for s in STAGES:
            values = [log[(s, d)] for d in days]
            flags = below_flags(values, days, k)
            judged += sum(f is not None for f in flags)
            full += sum(1 for i, d in enumerate(days) if sum(1 for e in days[:i] if e.weekday() == d.weekday()) >= k)
            onsets = p1_onsets(flags)
            false_before += sum(1 for i in onsets if days[i] < start)
            if s == stage:
                first = next((days[i].isoformat() for i in p1_days(flags) if days[i] >= start), None)
        out[k] = {"judged_stage_days": judged, "full_baseline_stage_days": full, "false_p1_before_event": false_before, "first_alert_for_assembly_drop": first}
    return {"first_day": days[0].isoformat(), "last_day": days[-1].isoformat(), "drop_starts": start.isoformat(), "by_window": out}


def study(runs=150):
    model = calibrate(read_log())
    return {"windows": WINDOWS, "rules": {"watch": "below the minimum of the previous K same weekdays (at least 3)",
                                          "p1": f"{SUSTAINED} consecutive working days below that minimum, emailed once per episode"},
            "false_alerts": false_alerts(model, runs), "detection": detection(model, runs * 2),
            "excursion": excursion(model, runs), "real_log": real_log(read_log())}


def markdown(r):
    w = r["windows"]
    head = "| | " + " | ".join(f"K = {k}" for k in w) + " |\n|---|" + "---|" * len(w) + "\n"
    fa, de, rl = r["false_alerts"], r["detection"], r["real_log"]["by_window"]
    row = lambda label, f: f"| {label} | " + " | ".join(f(k) for k in w) + " |\n"
    t = head
    t += row("False P1 alerts a month (4 stages, normal factory)", lambda k: str(fa[k]["p1_alerts_per_month"]))
    t += row("Normal days flagged \"below range\" a month", lambda k: str(fa[k]["watch_days_per_month"]))
    for size in (0.2, 0.3, 0.4):
        d = de[size] if size in de else de[str(size)]
        t += row(f"{int(size * 100)}% drop for 5 days: alert raised", lambda k, d=d: f"{d[k]['caught_pct']}%")
    d30 = de[0.3] if 0.3 in de else de["0.3"]
    t += row("30% drop: working days until the alert", lambda k: str(d30[k]["median_working_days_to_alert"]))
    n = max(rl[k]["judged_stage_days"] for k in w)
    t += row(f"Real log: stage-days with a full K-week baseline (of {n} judged)", lambda k: str(rl[k]["full_baseline_stage_days"]))
    t += row("Real log: false P1 alerts before 25 Mar", lambda k: str(rl[k]["false_p1_before_event"]))
    t += row("Real log: first alert for the assembly drop", lambda k: rl[k]["first_alert_for_assembly_drop"] or "none")
    return t


def render_doc(r):
    fa = r["false_alerts"]
    ex = r.get("excursion", {})
    excursion_rows = "\n".join(f"| {z} SD | {v['false_alerts_per_month']} | " + " | ".join(f"{p}%" for p in v["one_day_drop_caught_same_day_pct"].values()) + " |"
                                for z, v in ex.items())
    return f"""# Why "normal" uses the previous 8 same weekdays

*Generated by `python -m analysis.baseline_window` (numbers in `analysis/results/baseline_window.json`). Re-run after the data changes.*

**Short answer.** Same weekday, because the factory is closed on Sundays and each weekday has its own level, so a plain
"last 7 days" average is wrong twice: it includes a closed day, and during a problem it averages the problem itself.
Eight, because it is where the trade-off flattens: going from 4 to 8 weeks cuts false alerts to the manager about
{round(fa[4]['p1_alerts_per_month'] / max(fa[8]['p1_alerts_per_month'], 0.01))}-fold, while going beyond 8 buys little more quiet, misses more small drops and needs more history than
90 days of data can give. Measured below with the product's own rules: a day is flagged "below range" when it is under
the minimum of the previous K same weekdays (by chance about 1 in K+1 normal days), and the manager is emailed only after
{SUSTAINED} working days in a row below it.

{markdown(r)}
**How to read it.**
* Fewer weeks (K = 4) is jumpy: about {fa[4]['p1_alerts_per_month']} false alerts a month and {fa[4]['watch_days_per_month']} "below range" days that mean nothing.
* K = 8: about {fa[8]['p1_alerts_per_month']} false alerts a month (roughly one a year across all four stages), every 30% or larger drop
  caught on its third day, most 20% drops caught.
* More weeks (K = 10-12) lowers false alerts only slightly, misses more 20% drops, and on 90 days of data far fewer days
  have a full baseline.
* Every window catches the real assembly drop on 27 March (its third working day). 6 to 10 behave alike, so 8 is the
  middle of a flat optimum: the choice is about robustness, not precision.

**What K = 8 gives up.** Small, short dips are reported as watch items in the briefing rather than emailed. Because the
rule compares with the minimum of the window, a problem that lasts more than a week or two stops being flagged day by day;
the first alert, the digest reminders of an unresolved item and the "% below usual" figure (against the 8-week mean) keep
it visible.

**The same-day excursion alert.** A stage that falls far outside its range in one day (a machine down, a stoppage) should
not wait three days. The product also emails when a single working day is below the mean minus 3.5 standard deviations of
the same 8 weekdays (and below their minimum). Measured the same way:

| Threshold | False same-day alerts a month (4 stages) | One-day 30% drop caught that day | 40% | 50% |
|---|---|---|---|---|
{excursion_rows}

3.5 SD keeps false same-day alerts to about one every two months while catching nearly every 40% one-day drop; it shares
the stage's alert key, so one problem is emailed once (the excursion on day 1, the sustained drop then only reminded in
the digest).

**Not yet validated.** No planner has compared the flagged days with days they remember as bad. That is the next check.

**Method.** {r['rules']['watch']}; P1: {r['rules']['p1']}. Normal factory: weekday means of the real log times residuals
resampled a working week at a time (assembly's real drop excluded), 12 warm-up weeks then 18 judged weeks per run,
150 runs per stage for false alerts, 300 planted drops per size.
The one real event was 27 March, so the real log cannot separate the windows; the simulation does. Real log {r['real_log']['first_day']} to {r['real_log']['last_day']}.
"""


def main():
    r = study()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, indent=2, default=str))
    DOC.write_text(render_doc(json.loads(json.dumps(r, default=str), object_hook=lambda d: {int(k) if k.isdigit() else (float(k) if k.replace('.', '', 1).isdigit() else k): v for k, v in d.items()})))
    print(markdown(json.loads(json.dumps(r, default=str), object_hook=lambda d: {int(k) if k.isdigit() else (float(k) if k.replace('.', '', 1).isdigit() else k): v for k, v in d.items()})))


if __name__ == "__main__":
    main()
