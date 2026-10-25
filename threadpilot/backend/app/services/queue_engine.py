"""Queue projection adapted from PR #4 b0cc93e. Shared by risk and manager-reviewed scheduling."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import date, timedelta
from statistics import mean

from .queue_workdays import is_working, kth_working_day, prev_working, working_days_between, working_days_inclusive  # noqa: F401  (also re-exported for callers)

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
        # late_days_* mean the same thing on every branch: working days the finish lands AFTER the due date
        # (a 26 Oct review found the old value, working days from today, being read as "days after the due date").
        after_best = working_days_between(due, best_date)
        after_exp = working_days_between(due, exp_date) if exp_date else None
        return {**out, "level": "overdue", "confidence": "certain", "working_days_left": 0, "margin": 0,
                "days_past_due": late, "late_days_best": after_best, "late_days_expected": after_exp,
                "reason": f"{late} day{'s' if late != 1 else ''} past the {dm(due)} due date; finishes {dow_dm(best_date)} at best, "
                          f"{after_best} working day{'s' if after_best != 1 else ''} after the due date"}
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


# ---------------------------------------------------------------- shared analysis (pure Python; no database)
VERSION = 'queue-v1'
ASSUMPTIONS = [
    'Current orders only; identical capacity and arrivals (none) before and after an expedite.',
    'Monday–Saturday; current stage starts with full order quantity because partial progress is unavailable.',
    'Manager-approved priorities first, then earliest due date; at most one stage transition per day.',
    'Each order normally uses at most 60% of daily stage capacity (minimum allocation cap 20 pieces).',
    'Capacity: previous eight same weekdays, at least three samples per stage; historical completion factor capped at 1–3.',
    'No order value, customer weighting, penalty cost, overtime or guaranteed completion dates.',
    'An approved queue changes this application’s dispatch plan, not an external factory system.',
]


def fingerprint(data):
    """Stable digest of a snapshot so a review preview can detect data changes."""
    return hashlib.sha256(json.dumps({'algorithm': VERSION, **data}, sort_keys=True, default=str).encode()).hexdigest()



class QueueAnalysis:
    def __init__(self, data):
        self.data = data
        self.today = date.fromisoformat(data['today'])
        self.active = [dict(o, pieces=int(o['pieces'])) for o in data['orders'] if o['status'] == 'IN_PROGRESS']
        self.priority = [i for i in data.get('schedule', {}).get('priority', []) if i in {o['order_id'] for o in self.active}]
        target = prev_working(self.today)
        logs = [r for r in data['production_log'] if r['date'] < data['today'] and is_working(date.fromisoformat(r['date']))]
        self.samples = {}
        self.capacity = {}
        for stage in STAGES:
            rows = sorted([r for r in logs if r['stage'] == stage and r['date'] < target.isoformat()
                           and date.fromisoformat(r['date']).weekday() == target.weekday()], key=lambda r: r['date'])[-8:]
            self.samples[stage] = rows
            self.capacity[stage] = mean(float(r['pieces_completed']) for r in rows) if len(rows) >= 3 else None
        start = self.today - timedelta(days=60)
        completed = [o for o in data['orders'] if o['status'] == 'COMPLETE' and o.get('completed_date')
                     and start.isoformat() <= o['completed_date'] < data['today']]
        packing = [float(r['pieces_completed']) for r in logs if r['stage'] == 'PACKING' and r['date'] >= start.isoformat()]
        finished = sum(int(o['pieces']) for o in completed) / working_days_inclusive(start, self.today - timedelta(days=1))
        self.factor = round(min(3, max(1, finished / mean(packing))), 3) if len(completed) >= 10 and packing and mean(packing) > 0 else 1
        self.capacity = {s: value * self.factor if value is not None else None for s, value in self.capacity.items()}
        self.available = all(v is not None and v > 0 for v in self.capacity.values())
        self.base = project(self.active, self.capacity, self.today, priority=self.priority) if self.available else {}
        recent = prev_working(prev_working(self.today)).isoformat()
        self.stalled = {o['order_id'] for o in self.active
                        if working_days_between(date.fromisoformat(o['last_activity_date']), self.today) - 1 >= 5
                        and any(p['current_stage'] == o['current_stage'] and p['due_date'] > o['due_date']
                                and p['last_activity_date'] >= recent for p in self.active)}

    def context(self):
        return {'algorithm': VERSION, 'business_date': self.data['today'], 'fingerprint': fingerprint(self.data),
                'capacity': self.capacity, 'capacity_factor': self.factor, 'available': self.available,
                'schedule': self.data.get('schedule', {'version': 0, 'priority': []}), 'assumptions': ASSUMPTIONS,
                'sources': [{'url': f"/api/evidence/{name}/{r['_record_id']}", 'version': r.get('_version')}
                            for name in ('orders', 'production_log') for r in self.data[name] if '_record_id' in r]}

    def risk(self, order):
        oid = order['order_id']
        if order['status'] != 'IN_PROGRESS':
            return {'level': 'complete', 'reason': 'Completed order; no active dispatch risk.', 'best_date': None}
        if not self.available:
            return {'level': 'overdue' if order['due_date'] < self.data['today'] else 'unknown',
                    'reason': 'Insufficient positive production history for every stage.', 'best_date': None}
        result = assess_risk(order, self.base[oid], self.base[oid], self.today, oid in self.stalled)
        # This release intentionally uses one current-order scenario, including for risk.
        result['scenario'] = 'Current orders and approved dispatch priorities; no future arrivals'
        result['confidence_basis'] = 'Rule-based distance from due date, not a probability'
        return result

    def summary(self):
        return {**self.context(), 'orders': [{**o, 'risk': self.risk(o)} for o in self.active]}

    def expedite(self, oid):
        order = next((o for o in self.active if o['order_id'] == oid), None)
        if order is None:
            raise ValueError('Choose an existing in-progress order.')
        result = {**self.context(), 'order_id': oid, 'risk': self.risk(order), 'affected': [],
                  'gain': None, 'cost': None, 'net': None, 'finish_before': None, 'finish_after': None,
                  'recommendation': 'unavailable', 'can_apply': False}
        if not self.available:
            return {**result, 'reason': 'Insufficient production history; do not adjust from this estimate.'}
        fast = project(self.active, self.capacity, self.today, expedite_id=oid, priority=self.priority)
        if any(self.base[o['order_id']] is None or fast[o['order_id']] is None for o in self.active):
            return {**result, 'reason': 'At least one order exceeds the 200-working-day horizon; impact cannot be quantified.'}
        def lateness(o, k):
            return max(0, k - working_days_inclusive(self.today, date.fromisoformat(o['due_date'])))
        gain = lateness(order, self.base[oid]) - lateness(order, fast[oid])
        affected = []
        for other in self.active:
            key = other['order_id']
            if key == oid or fast[key] == self.base[key]:
                continue
            before, after = lateness(other, self.base[key]), lateness(other, fast[key])
            affected.append({'order_id': key, 'customer': other['customer'], 'extra_days': fast[key] - self.base[key],
                             'added_lateness': after - before, 'newly_late': before == 0 and after > 0,
                             'finish_before': kth_working_day(self.today, self.base[key]).isoformat(),
                             'finish_after': kth_working_day(self.today, fast[key]).isoformat()})
        cost = sum(r['added_lateness'] for r in affected)
        net = gain - cost
        if oid in self.stalled:
            recommendation, reason = 'investigate', 'Suspected stalled order: verify the blocker before changing its queue priority.'
        elif gain < 2 or net < 2:
            recommendation, reason = 'later', 'Less than two order-working-days of lateness saved for this order or across the queue.'
        elif any(r['newly_late'] for r in affected):
            recommendation, reason = 'trade_off', 'Net benefit, but some previously on-time orders become late; manager review required.'
        else:
            recommendation, reason = 'now', 'Net benefit of at least two order-working-days without making an on-time order late.'
        return {**result, 'gain': gain, 'cost': cost, 'net': net, 'affected': affected,
                'days_saved': self.base[oid] - fast[oid], 'recommendation': recommendation, 'reason': reason,
                'can_apply': oid not in self.stalled and self.risk(order)['level'] in ('overdue', 'high', 'medium')
                             and self.base[oid] > fast[oid],
                'finish_before': kth_working_day(self.today, self.base[oid]).isoformat(),
                'finish_after': kth_working_day(self.today, fast[oid]).isoformat()}
