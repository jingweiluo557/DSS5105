"""The GM home screen in one payload: a status line, the decisions only the manager can make, order health and the
production pulse. Built for the ten-second test (docs/CEO_INTERFACE_REVIEW.md): the first screen says what to decide
today before it shows any counter.

Pure Python over the same snapshot the chat tools and the alert policy use; no database, no model. The decision cards
come from alert_policy.detect (P1 first, then P2), so the home screen, the alert emails and the find_anomalies tool
never disagree about what matters.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import mean

from . import alert_policy
from .queue_engine import QueueAnalysis, STAGES, is_working

COLOUR_MEANING = {
    'red': 'A decision today changes the outcome.',
    'amber': 'Decide today; nothing is lost yet.',
    'green': 'Nothing needs you; the briefing has the detail.',
}
MAX_CARDS = 3
SAME_WEEKDAY_SAMPLES = 8
MIN_SAMPLES = 3


def _dm(value: str | date) -> str:
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return f"{d.day} {d.strftime('%b')}"


def _pieces(order: dict) -> str:
    return f"{int(float(order['pieces'])):,}"


# ---------------------------------------------------------------- production pulse: latest working day against its same-weekday band
def stage_pulse(data: dict, today: date) -> list[dict]:
    """One row per stage: the latest working-day output, the previous-8-same-weekday band (the normality rule the chat
    uses), where the value sits against it, and how many consecutive working days it has been below the band."""
    logs = sorted((r for r in data['production_log'] if r['date'] < today.isoformat() and is_working(date.fromisoformat(r['date']))), key=lambda r: r['date'])
    out = []
    for stage in STAGES:
        rows = [r for r in logs if r['stage'] == stage]
        if not rows:
            out.append({'stage': stage, 'date': None, 'pieces': None, 'band': None, 'status': 'no_record', 'change_pct': None, 'below_days': 0, 'below_since': None})
            continue

        def band_for(day: date):
            base = [int(float(x['pieces_completed'])) for x in rows if date.fromisoformat(x['date']) < day and date.fromisoformat(x['date']).weekday() == day.weekday()][-SAME_WEEKDAY_SAMPLES:]
            return {'min': min(base), 'max': max(base), 'mean': round(mean(base), 1), 'samples': len(base)} if len(base) >= MIN_SAMPLES else None

        latest = rows[-1]
        day = date.fromisoformat(latest['date'])
        pieces = int(float(latest['pieces_completed']))
        band = band_for(day)
        status = 'no_baseline' if band is None else 'below' if pieces < band['min'] else 'above' if pieces > band['max'] else 'within'
        below_days, below_since = 0, None
        for r in reversed(rows):
            b = band_for(date.fromisoformat(r['date']))
            if b is None or int(float(r['pieces_completed'])) >= b['min']:
                break
            below_days, below_since = below_days + 1, r['date']
        out.append({'stage': stage, 'date': latest['date'], 'pieces': pieces, 'band': band, 'status': status,
                    'change_pct': round(100 * (pieces / band['mean'] - 1)) if band else None,
                    'below_days': below_days, 'below_since': below_since})
    return out


# ---------------------------------------------------------------- order health: one vocabulary (late / at risk / on track)
def health(engine: QueueAnalysis, data: dict, today: date) -> dict:
    late = at_risk = on_track = unknown = 0
    for o in engine.active:
        level = engine.risk(o)['level']
        if level == 'overdue':
            late += 1
        elif level in ('high', 'medium'):
            at_risk += 1
        elif level == 'low':
            on_track += 1
        else:
            unknown += 1

    def delivery(start: date, end: date) -> dict:
        rows = [r for r in data['orders'] if r['status'] == 'COMPLETE' and r.get('completed_date') and start.isoformat() <= r['completed_date'] < end.isoformat()]
        on_time = sum(float(r['days_late'] or 0) <= 0 for r in rows)
        return {'total': len(rows), 'on_time': on_time, 'rate': round(on_time / len(rows) * 100) if rows else None}

    current, prior = delivery(today - timedelta(days=30), today), delivery(today - timedelta(days=60), today - timedelta(days=30))
    return {'late': late, 'at_risk': at_risk, 'on_track': on_track, 'unknown': unknown, 'active': len(engine.active),
            'on_time_rate': current['rate'], 'on_time_basis': f"{current['on_time']} of {current['total']} completed in the last 30 days",
            'on_time_change_pts': (current['rate'] - prior['rate']) if current['rate'] is not None and prior['rate'] is not None else None,
            'vocabulary': 'late = past the due date; at risk = the shared queue cannot finish it by the due date in the best or the expected case; on track = finishes in time even if new orders go ahead of it'}


# ---------------------------------------------------------------- decisions: alert → card with one button
def _card(a: alert_policy.Alert, engine: QueueAnalysis, data: dict, today: date, pulse: list[dict]) -> dict | None:
    orders = {o['order_id']: o for o in engine.active}
    o = orders.get(a.entity)
    base = {'key': a.key, 'tier': a.tier, 'kind': a.kind, 'entity': a.entity, 'rule': a.rule, 'score': a.score}
    if a.kind == 'stage_drop':
        row = next((p for p in pulse if p['stage'] == a.entity), None)
        ev = a.evidence or []
        gap = -row['change_pct'] if row and row['change_pct'] is not None else (round(100 * (1 - mean(b['output'] / b['mean'] for b in ev))) if ev else None)
        days = row['below_days'] if row and row['below_days'] else len(ev)
        since = row['below_since'] if row and row['below_since'] else (ev[0]['date'] if ev else None)
        index = STAGES.index(a.entity)
        queued = sum(1 for x in engine.active if STAGES.index(x['current_stage']) <= index) if a.entity in STAGES else 0
        return {**base, 'title': f"{a.entity.title()} {gap}% below range" if gap is not None else f"{a.entity.title()} below range",
                'lines': [f"{days} working days below its normal range" + (f", since {_dm(since)}" if since else ''),
                          f"{queued} active orders still have to pass {a.entity.lower()}"],
                'action': {'label': 'Ask the floor', 'kind': 'chat',
                           'message': f"Draft a chase-up to the {a.entity.lower()} department: output has been below its normal range for {days} working days ({gap}% under). Ask what changed and when it will recover. Show the draft before sending."}}
    if a.kind == 'will_miss' and o:
        risk = engine.risk(o)
        return {**base, 'title': f"{o['order_id']} will miss {_dm(o['due_date'])}",
                'lines': [f"{o['customer']}, {_pieces(o)} {o['product']}, at {o['current_stage'].lower()}",
                          f"best case {_dm(risk['best_date'])}" + (f"; expected {_dm(risk['expected_date'])}" if risk.get('expected_date') and risk['expected_date'] != risk['best_date'] else '')],
                'action': {'label': 'Review options', 'kind': 'route', 'value': f"risk?id={o['order_id']}"},
                'options': ['expedite', 'outsource', 'new date']}
    if a.kind == 'customer_stalled':
        n = len(a.evidence or [])
        return {**base, 'title': f"All {n} {a.entity} orders stopped",
                'lines': [a.title.split('(')[-1].rstrip(')') if '(' in a.title else a.detail, 'later-due orders at the same stage moved; the queue does not explain it'],
                'action': {'label': 'Call the customer', 'kind': 'chat',
                           'message': f"Draft a chase-up to the planner about {a.entity}: all {n} active orders have stopped moving while later-due orders at the same stage moved. Ask for the blocker. Show the draft before sending."}}
    if a.kind == 'overdue' and o:
        days = (today - date.fromisoformat(o['due_date'])).days
        risk = engine.risk(o)
        return {**base, 'title': f"{o['order_id']} is {days} day{'s' if days != 1 else ''} late",
                'lines': [f"{o['customer']}, {_pieces(o)} {o['product']}, still at {o['current_stage'].lower()}",
                          f"finishes {_dm(risk['best_date'])} at best" if risk.get('best_date') else 'finish date unavailable'],
                'action': {'label': 'Confirm a new date', 'kind': 'route', 'value': f"risk?id={o['order_id']}"}}
    if a.kind == 'high_risk' and o:
        risk = engine.risk(o)
        return {**base, 'title': f"{o['order_id']} at risk, due {_dm(o['due_date'])}",
                'lines': [f"{o['customer']}, {_pieces(o)} {o['product']}, at {o['current_stage'].lower()}",
                          f"best case {_dm(risk['best_date'])}" if risk.get('best_date') else risk['reason']],
                'action': {'label': 'Review options', 'kind': 'route', 'value': f"risk?id={o['order_id']}"}}
    if a.kind == 'new_large_or_rush' and o:
        return {**base, 'title': f"New order {o['order_id']}: {_pieces(o)} {o['product']}",
                'lines': [f"{o['customer']}, due {_dm(o['due_date'])}", 'check capacity before the planner commits'],
                'action': {'label': 'Check feasibility', 'kind': 'route', 'value': 'feasibility'}}
    return None


def decisions(alerts: list[alert_policy.Alert], engine: QueueAnalysis, data: dict, today: date, pulse: list[dict], limit: int = MAX_CARDS) -> tuple[list[dict], int]:
    """At most `limit` cards, one per entity, P1 before P2 (P3 never earns a card). Returns (cards, how many more
    P1/P2 items wait behind them)."""
    cards, seen = [], set()
    pool = [a for a in alerts if a.tier in (alert_policy.P1, alert_policy.P2)]
    for a in pool:
        if a.entity in seen:
            continue
        card = _card(a, engine, data, today, pulse)
        if card is None:
            continue
        seen.add(a.entity)
        cards.append(card)
        if len(cards) >= limit:
            break
    waiting = len({a.entity for a in pool} - seen)
    return cards, waiting


# ---------------------------------------------------------------- the status line
def status_line(alerts: list[alert_policy.Alert], counts: dict, pulse: list[dict], cards: list[dict], today: date) -> dict:
    tiers = {a.tier for a in alerts}
    colour = 'red' if alert_policy.P1 in tiers else 'amber' if alert_policy.P2 in tiers else 'green'
    facts = [f"{counts['overdue']} overdue" if counts['overdue'] != 1 else '1 overdue']
    worst = min((p for p in pulse if p['change_pct'] is not None and p['status'] == 'below'), key=lambda p: p['change_pct'], default=None)
    if worst:
        facts.append(f"{worst['stage'].title()} {worst['change_pct']}% " + (f"for {worst['below_days']} days" if worst['below_days'] >= 2 else 'yesterday'))
    elif counts['due_today']:
        facts.append(f"{counts['due_today']} due today")
    facts.append(f"{len(cards)} decision{'s' if len(cards) != 1 else ''} need you" if cards else 'no decisions waiting')
    return {'colour': colour, 'label': colour.upper(), 'date': today.isoformat(), 'date_label': f"{today:%a} {today.day} {today:%b}",
            'facts': facts, 'meaning': COLOUR_MEANING[colour]}


def home(data: dict, now: datetime) -> dict:
    today = now.date()
    engine = QueueAnalysis(data)
    alerts = alert_policy.detect(data, now)
    pulse = stage_pulse(data, today)
    active = engine.active
    counts = {'in_progress': len(active),
              'overdue': sum(o['due_date'] < today.isoformat() for o in active),
              'due_today': sum(o['due_date'] == today.isoformat() for o in active),
              'idle': sum((today - date.fromisoformat(o['last_activity_date'])).days >= 5 for o in active),
              'total': len(data['orders'])}
    cards, waiting = decisions(alerts, engine, data, today, pulse)
    return {'business_date': today.isoformat(), 'as_of': now.isoformat(),
            'status': status_line(alerts, counts, pulse, cards, today),
            'decisions': cards, 'more_waiting': waiting,
            'alerts': {t: sum(a.tier == t for a in alerts) for t in (alert_policy.P1, alert_policy.P2, alert_policy.P3)},
            'counts': counts, 'health': health(engine, data, today), 'pulse': pulse,
            'basis': 'Decisions come from the alert policy (docs/ALERT_POLICY.md); health from the shared queue projection; '
                     'the pulse band is the previous eight same-weekday records, the rule check_normality uses.'}
