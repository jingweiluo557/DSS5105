"""Queue projection adapted from PR #4 b0cc93e. Shared by risk and manager-reviewed scheduling."""
from __future__ import annotations

import math
from collections import Counter
from datetime import date, timedelta
from statistics import mean

from .queue_workdays import is_working, kth_working_day, working_days_inclusive  # noqa: F401  (also re-exported for callers)

STAGES = ["KNITTING", "ASSEMBLY", "WASHING", "PACKING"]
CAP = 200                  # working days to look ahead before giving up
SERVICE_SHARE = 0.6        # one order can use at most this share of a stage's daily output per day
MIN_DAYS_SAVED = 2         # expediting must save at least this many working days to be worth recommending
CONFIDENCE_HIGH = 5        # working days between the estimate and the due date for "high" confidence
CONFIDENCE_MEDIUM = 2
HIGH_LATE_DAYS = 5          # even the best case this many working days past the due date = high risk
STALLED_NEAR_DUE_DAYS = 10 # a stalled order due within this many working days is rated high risk
FORECAST_HORIZON = 12      # working days (two weeks)
FORECAST_WINDOW = 60       # calendar days of order history used
MIN_FORECAST_ORDERS = 10
LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}


# ---------------------------------------------------------------- formatting (calendar helpers live in workdays.py)
def dm(d: date) -> str:
    """'9 Apr'. Written by hand because strftime's no-padding flag is not portable (it fails on Windows)."""
    return f"{d.day} {d.strftime('%b')}"


def dow_dm(d: date) -> str:
    return f"{d.strftime('%a')} {dm(d)}"


# ---------------------------------------------------------------- the projection engine
def project(active: list[dict], cap: dict, business_date: date, expedite_id: str | None = None,
            arrivals: dict | None = None, priority: list[str] | None = None) -> dict[str, int | None]:
    """Working-day index (1 = the business date if it is a working day) at which each active order finishes, or None if
    it does not finish within CAP working days. `cap` is the daily output per stage."""
    rank = {oid: i for i, oid in enumerate(priority or [])}
    work = [{"id": o["order_id"], "pieces": float(o["pieces"]), "stage": STAGES.index(o["current_stage"]),
             "need": float(o["pieces"]), "due": o["due_date"], "real": True} for o in active]
    finish: dict[str, int | None] = {o["order_id"]: None for o in active}
    open_real = len(active)
    lead = None
    if arrivals and arrivals["leads"]:
        leads = sorted(arrivals["leads"])
        lead = leads[len(leads) // 2]
    d, k, syn = business_date - timedelta(days=1), 0, 0
    while open_real and k < CAP:
        d += timedelta(days=1)
        if not is_working(d):
            continue
        k += 1
        if lead is not None:  # one average-sized order a day, due after the usual lead time
            syn += 1
            work.append({"id": f"~{syn}", "pieces": arrivals["pieces_per_working_day"], "stage": 0,
                         "need": arrivals["pieces_per_working_day"], "due": (d + timedelta(days=lead)).isoformat(), "real": False})
        moved: set[str] = set()
        for si in reversed(range(len(STAGES))):
            left = cap[STAGES[si]]
            per_order = SERVICE_SHARE * cap[STAGES[si]]
            queue = [w for w in work if w["stage"] == si and w["id"] not in moved]
            queue.sort(key=lambda w: (-1, "", "") if w["id"] == expedite_id else (rank.get(w["id"], len(rank)), w["due"], w["id"]))
            for w in queue:
                if left <= 1e-9:
                    break
                take = min(w["need"], left, max(20.0, per_order))
                w["need"] -= take
                left -= take
                if w["need"] <= 1e-9:
                    if si == len(STAGES) - 1:
                        w["stage"] = len(STAGES)
                        if w["real"]:
                            finish[w["id"]] = k
                            open_real -= 1
                    else:
                        w["stage"] = si + 1
                        w["need"] = w["pieces"]
                        moved.add(w["id"])
        work = [w for w in work if w["stage"] < len(STAGES)]
    return finish


# ---------------------------------------------------------------- risk
def assess_risk(x: dict, best_k: int | None, exp_k: int | None, business_date: date, stalled: bool) -> dict:
    due = date.fromisoformat(x["due_date"])
    unfinished = best_k is None            # does not finish within CAP working days even with no new orders
    best_k = best_k or CAP
    best_date = kth_working_day(business_date, best_k)
    exp_date = kth_working_day(business_date, exp_k) if exp_k else None
    out = {"best_date": best_date.isoformat(), "expected_date": exp_date.isoformat() if exp_date else None,
           "stalled": stalled, **({"unfinished": True} if unfinished else {})}
    if due < business_date:
        late = (business_date - due).days
        return {**out, "level": "overdue", "confidence": "certain", "working_days_left": 0, "margin": 0,
                "late_days_best": best_k, "late_days_expected": exp_k,
                "reason": f"{late} day{'s' if late != 1 else ''} past the {dm(due)} due date"}
    width = working_days_inclusive(business_date, due)
    late_best = max(0, best_k - width)
    if late_best >= HIGH_LATE_DAYS:
        level, margin = "high", late_best
    elif late_best >= 1:
        level, margin = "medium", late_best
    elif exp_k is None or exp_k > width:
        level = "medium"
        margin = min(width - best_k, (exp_k - width) if exp_k is not None else 99)
    else:
        level, margin = "low", width - exp_k
    if late_best >= 1:
        reason = (f"Even in the best case it finishes {dow_dm(best_date)}, {late_best} working day{'s' if late_best != 1 else ''} "
                  f"after the {dm(due)} due date")
    elif level == "medium":
        reason = (f"Finishes {dm(best_date)} at best, {dm(exp_date)} if new orders go ahead of it; due {dm(due)}"
                  if exp_date else f"Finishes {dm(best_date)} at best and may not finish at all if new orders keep going ahead; due {dm(due)}")
    else:
        reason = f"Should finish by {dow_dm(exp_date)}, before the {dm(due)} due date"
    if unfinished:   # no date to show: say so instead of quoting the CAP-th working day as if it were an estimate
        level, margin = "high", CAP
        reason = f"Does not finish within {CAP} working days even in the best case; due {dm(due)}"
    confidence = "high" if margin >= CONFIDENCE_HIGH else "medium" if margin >= CONFIDENCE_MEDIUM else "low"
    if stalled:  # the projection assumes the order moves; a stalled one breaks that assumption
        bumped = "high" if width <= STALLED_NEAR_DUE_DAYS else "medium"
        if LEVEL_RANK[bumped] > LEVEL_RANK[level]:
            level = bumped
        confidence = "medium" if confidence == "high" else confidence
        reason = "Not moving, and the projection assumes it moves. " + reason
    return {**out, "level": level, "confidence": confidence, "working_days_left": width, "margin": margin,
            "late_days_best": late_best, "late_days_expected": (max(0, exp_k - width) if exp_k else None), "reason": reason}


