"""Alert policy: when does ThreadPilot interrupt the general manager, and when does it wait for the briefing?

Design rules (written down so they can be audited and tuned; see docs/ALERT_POLICY.md):
  1. An interruption is earned only by something that (a) needs a decision or action from the GM today, (b) the system
     cannot handle on its own, and (c) is new or materially worse than what was already reported.
  2. Three tiers, like an alarm philosophy (ISA-18.2) or an on-call rota: P1 "act now" emails at once; P2 "decide today"
     is batched into at most two digests (07:00 briefing, 14:00); P3 "watch" never emails: it appears in the briefing
     and the app.
  3. Every alert has a dedupe key; the same key is not sent again within its cooldown unless its score rose by at least
     ESCALATION_STEP. Clearing never sends an email (the briefing says "cleared").
  4. Hard caps: at most MAX_P1_PER_DAY immediate emails a day; beyond that, one "several critical items" email and the
     rest go to the digest. Quiet hours hold P2/P3; P1 goes through.
  5. Manager can shelve a key or a kind for N days ("mute this for a week"); shelved alerts stay visible in the app.

This module is pure Python over the snapshot the queue tools already use: no database, no network, no model. Delivery
(Outlook) is a separate, flagged step in alert_delivery.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from statistics import mean

from .queue_engine import QueueAnalysis, STAGES, is_working, working_days_between

P1, P2, P3 = 'P1', 'P2', 'P3'
ESCALATION_STEP = 8
MAX_P1_PER_DAY = 3
COOLDOWN_HOURS = {P1: 24, P2: 24 * 3, P3: 24 * 7}
QUIET_HOURS = (22, 6)                 # local time; P2/P3 wait for the next digest, P1 passes
DIGEST_HOURS = (7, 14)                # P2 digests
SUSTAINED_DROP_DAYS = 3               # consecutive working days below the same-weekday minimum
EXCURSION_SIGMA = 3.5                 # one working day this far under the same-weekday mean is an excursion (P1 the same day)
EXCURSION_MIN_SAMPLES = 5             # analysis/baseline_window.py: ~0.47 false excursions a month over 4 stages;
                                      # a one-day 40% drop caught the same day 94% of the time, 50% always
STALLED_CUSTOMER_MIN_ORDERS = 2
NEAR_DUE_WORKING_DAYS = 2
LARGE_ORDER_PIECES = 1500
RUSH_LEAD_DAYS = 12


@dataclass
class Alert:
    key: str                       # dedupe key: kind:entity
    kind: str
    tier: str
    score: int                     # 0-100, used for ordering and escalation
    title: str                     # one line, fits a subject
    detail: str                    # the numbers behind it
    entity: str                    # order id, customer, stage
    action: str                    # what the GM is expected to do
    evidence: list[dict] = field(default_factory=list)
    rule: str = ''

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- detection
def detect(data: dict, now: datetime) -> list[Alert]:
    """All alert candidates for the current snapshot. No history applied yet."""
    today = now.date()
    engine = QueueAnalysis(data)
    active = engine.active
    logs = sorted(data['production_log'], key=lambda r: r['date'])
    out: list[Alert] = []

    # P1-a: a stage below its same-weekday minimum for SUSTAINED_DROP_DAYS consecutive working days
    for stage in STAGES:
        rows = [r for r in logs if r['stage'] == stage]
        recent = [r for r in rows if date.fromisoformat(r['date']) < today and is_working(date.fromisoformat(r['date']))][-SUSTAINED_DROP_DAYS:]
        if len(recent) < SUSTAINED_DROP_DAYS:
            continue
        below = []
        for r in recent:
            d = date.fromisoformat(r['date'])
            base = [int(x['pieces_completed']) for x in rows if date.fromisoformat(x['date']) < d and date.fromisoformat(x['date']).weekday() == d.weekday()][-8:]
            if len(base) >= 3 and int(r['pieces_completed']) < min(base):
                below.append({'date': r['date'], 'output': int(r['pieces_completed']), 'same_weekday_min': min(base), 'mean': round(mean(base), 1)})
        if len(below) == SUSTAINED_DROP_DAYS:
            gap = round(100 * (1 - mean(b['output'] / b['mean'] for b in below)))
            out.append(Alert(key=f'stage_drop:{stage}', kind='stage_drop', tier=P1, score=min(100, 60 + gap), entity=stage,
                             title=f'{stage.title()} has been below its normal range for {SUSTAINED_DROP_DAYS} working days ({gap}% under)',
                             detail='; '.join(f"{b['date']}: {b['output']} vs min {b['same_weekday_min']} (mean {b['mean']})" for b in below),
                             action='Ask the floor what changed; check which near-due orders sit at or after this stage.',
                             evidence=below, rule=f'{SUSTAINED_DROP_DAYS} consecutive working days below the previous-8-same-weekday minimum'))

    # P1-a2: a sudden excursion: the latest working day far outside the stage's normal range (machine down, a stoppage).
    # It shares the stage's key with the sustained drop, so one problem emails once: day 1 as an excursion, and on
    # day 3 the sustained drop is only reminded in the digest (cooldown), unless it got materially worse.
    for stage in STAGES:
        if any(a.key == f'stage_drop:{stage}' for a in out):
            continue
        rows = [r for r in logs if r['stage'] == stage]
        worked = [r for r in rows if date.fromisoformat(r['date']) < today and is_working(date.fromisoformat(r['date']))]
        if not worked:
            continue
        r = worked[-1]
        d = date.fromisoformat(r['date'])
        if (today - d).days > 3:
            continue   # stale data is not an excursion
        base = [int(x['pieces_completed']) for x in rows if date.fromisoformat(x['date']) < d and date.fromisoformat(x['date']).weekday() == d.weekday()][-8:]
        if len(base) < EXCURSION_MIN_SAMPLES:
            continue
        m = mean(base)
        sd = (sum((b - m) ** 2 for b in base) / len(base)) ** 0.5
        value = int(r['pieces_completed'])
        if value < min(base) and value < m - EXCURSION_SIGMA * sd:
            gap = round(100 * (1 - value / m)) if m else 100
            out.append(Alert(key=f'stage_drop:{stage}', kind='stage_excursion', tier=P1, score=min(100, 55 + gap), entity=stage,
                             title=f'{stage.title()} made {value} pieces on {r["date"]}, {gap}% under its usual {round(m)}: far outside its normal range',
                             detail=f'{r["date"]}: {value} against the previous {len(base)} same weekdays (mean {round(m, 1)}, lowest {min(base)}, SD {round(sd, 1)})',
                             action='Ask the floor what happened (a stoppage, absence or material); if it continues, near-due orders behind this stage slip.',
                             evidence=[{'date': r['date'], 'output': value, 'same_weekday_mean': round(m, 1), 'same_weekday_min': min(base), 'sd': round(sd, 1)}],
                             rule=f'one working day below the mean minus {EXCURSION_SIGMA} SD of the previous 8 same weekdays (at least {EXCURSION_MIN_SAMPLES}) and below their minimum'))

    # P1-b: a customer whose active orders have all stalled while later-due orders moved (shared cause, not the queue)
    by_customer: dict[str, list[dict]] = {}
    for o in active:
        by_customer.setdefault(o['customer'], []).append(o)
    for customer, orders in by_customer.items():
        stalled = [o for o in orders if o['order_id'] in engine.stalled]
        if len(orders) >= STALLED_CUSTOMER_MIN_ORDERS and len(stalled) == len(orders):
            idle = max(working_days_between(date.fromisoformat(o['last_activity_date']), today) - 1 for o in orders)
            out.append(Alert(key=f'customer_stalled:{customer}', kind='customer_stalled', tier=P1, score=min(100, 70 + 2 * len(orders)), entity=customer,
                             title=f'All {len(orders)} active {customer} orders have stopped moving ({idle} working days)',
                             detail=', '.join(f"{o['order_id']} last {o['last_activity_date']}" for o in orders),
                             action='A shared cause (hold, materials, payment) is more likely than the queue; call the customer contact or the planner.',
                             evidence=[{'order_id': o['order_id'], 'last_activity_date': o['last_activity_date']} for o in orders],
                             rule='every active order of the customer idle >= 5 working days while a later-due order at the same stage moved'))

    # P1-c: due within NEAR_DUE_WORKING_DAYS and the queue cannot finish it even in the best case (and no manager priority)
    for o in active:
        due = date.fromisoformat(o['due_date'])
        if due < today:
            continue
        width = working_days_between(today, due)
        if width <= NEAR_DUE_WORKING_DAYS and engine.available:
            risk = engine.risk(o)
            late = risk.get('late_days_best') or 0
            if late >= 1 and o['order_id'] not in engine.priority:
                out.append(Alert(key=f'will_miss:{o["order_id"]}', kind='will_miss', tier=P1, score=min(100, 75 + late), entity=o['order_id'],
                                 title=f"{o['order_id']} ({o['customer']}, {o['pieces']} {o['product']}) due {o['due_date']} will miss even in the best case",
                                 detail=risk['reason'], action='Decide today: expedite (review the queue impact), outsource, or tell the customer a new date.',
                                 evidence=[{'order_id': o['order_id'], 'best_date': risk.get('best_date'), 'due_date': o['due_date']}],
                                 rule=f'due within {NEAR_DUE_WORKING_DAYS} working days and best-case finish after the due date, no approved priority'))

    # P2: newly overdue; newly high risk; new large or rush order; near-due orders still at knitting
    for o in active:
        due = date.fromisoformat(o['due_date'])
        if due < today:
            days = (today - due).days
            out.append(Alert(key=f'overdue:{o["order_id"]}', kind='overdue', tier=P2, score=min(90, 50 + 4 * days), entity=o['order_id'],
                             title=f"{o['order_id']} ({o['customer']}) is {days} day{'s' if days != 1 else ''} overdue, still at {o['current_stage']}",
                             detail=f"due {o['due_date']}, last activity {o['last_activity_date']}", action='Confirm the customer has a new date; chase the stage if idle.',
                             evidence=[{'order_id': o['order_id'], 'due_date': o['due_date']}], rule='IN_PROGRESS and due_date before the business date'))
        elif engine.available and engine.risk(o)['level'] == 'high':
            r = engine.risk(o)
            out.append(Alert(key=f'high_risk:{o["order_id"]}', kind='high_risk', tier=P2, score=min(85, 55 + (r.get('late_days_best') or 0) * 3), entity=o['order_id'],
                             title=f"{o['order_id']} ({o['customer']}) is at high risk: {r['reason']}", detail=f"due {o['due_date']}, best case {r.get('best_date')}",
                             action='Review in the morning: expedite analysis or an early word to the customer.',
                             evidence=[{'order_id': o['order_id'], 'best_date': r.get('best_date')}], rule='shared queue risk level high'))
        lead = (due - date.fromisoformat(o['order_date'])).days
        if o['order_date'] == (today - timedelta(days=1)).isoformat() and (int(o['pieces']) >= LARGE_ORDER_PIECES or lead <= RUSH_LEAD_DAYS):
            out.append(Alert(key=f'new_large_or_rush:{o["order_id"]}', kind='new_large_or_rush', tier=P2, score=50, entity=o['order_id'],
                             title=f"New {'rush ' if lead <= RUSH_LEAD_DAYS else ''}order {o['order_id']}: {o['pieces']} {o['product']} for {o['customer']}, {lead}-day lead",
                             detail=f"ordered {o['order_date']}, due {o['due_date']}", action='Check the feasibility estimate before the planner commits.',
                             evidence=[{'order_id': o['order_id']}], rule=f'ordered yesterday and (pieces >= {LARGE_ORDER_PIECES} or lead <= {RUSH_LEAD_DAYS} days)'))

    # P3: single low day; idle >= 5 calendar days but not near due; medium risk
    yesterday = today - timedelta(days=1)
    for stage in STAGES:
        rows = [r for r in logs if r['stage'] == stage]
        obs = next((r for r in rows if r['date'] == yesterday.isoformat()), None)
        if obs and is_working(yesterday):
            base = [int(x['pieces_completed']) for x in rows if date.fromisoformat(x['date']) < yesterday and date.fromisoformat(x['date']).weekday() == yesterday.weekday()][-8:]
            if len(base) >= 3 and int(obs['pieces_completed']) < min(base) and not any(a.key == f'stage_drop:{stage}' for a in out):
                out.append(Alert(key=f'low_day:{stage}:{yesterday}', kind='low_day', tier=P3, score=40, entity=stage,
                                 title=f"{stage.title()} output {obs['pieces_completed']} yesterday, below its same-weekday range ({min(base)}-{max(base)})",
                                 detail='one observation; not proof of a sustained problem', action='None yet; watch today.',
                                 evidence=[{'date': yesterday.isoformat(), 'output': int(obs['pieces_completed'])}], rule='one day below the previous-8-same-weekday minimum'))
    for o in active:
        idle = (today - date.fromisoformat(o['last_activity_date'])).days
        if idle >= 5 and not any(a.entity == o['order_id'] for a in out):
            out.append(Alert(key=f'idle:{o["order_id"]}', kind='idle', tier=P3, score=min(60, 30 + 3 * idle), entity=o['order_id'],
                             title=f"{o['order_id']} ({o['customer']}) has no recorded activity for {idle} days", detail=f"due {o['due_date']}, stage {o['current_stage']}",
                             action='Ask for a status if it is still quiet tomorrow.', evidence=[{'order_id': o['order_id'], 'last_activity_date': o['last_activity_date']}],
                             rule='calendar days since last_activity_date >= 5'))
    out.sort(key=lambda a: ({P1: 0, P2: 1, P3: 2}[a.tier], -a.score, a.key))
    return out


# ---------------------------------------------------------------- gating (history, cooldown, caps, shelving, quiet hours)
@dataclass
class Decision:
    alert: Alert
    channel: str          # 'email_now' | 'digest' | 'briefing_only' | 'suppressed'
    reason: str


def gate(alerts: list[Alert], history: list[dict], now: datetime, shelved: dict[str, str] | None = None) -> list[Decision]:
    """Apply the anti-spam rules. history = past decisions [{key, tier, score, sent_at(iso), channel}]; shelved = {key_or_kind: until_iso}."""
    shelved = shelved or {}
    last: dict[str, dict] = {}
    for h in sorted(history, key=lambda h: h['sent_at']):
        if h.get('channel') in ('email_now', 'digest'):
            last[h['key']] = h
    sent_today = sum(1 for h in history if h.get('channel') == 'email_now' and h['sent_at'][:10] == now.date().isoformat())
    quiet = now.hour >= QUIET_HOURS[0] or now.hour < QUIET_HOURS[1]
    decisions: list[Decision] = []
    for a in alerts:
        until = shelved.get(a.key) or shelved.get(a.kind)
        if until and until >= now.isoformat():
            decisions.append(Decision(a, 'suppressed', f'shelved by the manager until {until[:10]}'))
            continue
        prev = last.get(a.key)
        if prev and a.score < prev['score'] + ESCALATION_STEP:
            age_h = (now - datetime.fromisoformat(prev['sent_at'])).total_seconds() / 3600
            if age_h < COOLDOWN_HOURS[a.tier]:
                decisions.append(Decision(a, 'suppressed', f'already reported {age_h:.0f} h ago (score {prev["score"]} -> {a.score}, no escalation)'))
            elif a.tier == P3:
                decisions.append(Decision(a, 'briefing_only', 'still open; watch item stays in the briefing'))
            else:
                # An unresolved item is never re-emailed on its own: it is reminded in the next digest / briefing.
                decisions.append(Decision(a, 'digest', f'still open after {age_h / 24:.0f} days, not escalated; reminder in the digest, no new email'))
            continue
        if a.tier == P1:
            if sent_today >= MAX_P1_PER_DAY:
                decisions.append(Decision(a, 'digest', f'daily cap of {MAX_P1_PER_DAY} immediate emails reached; included in the next digest'))
            else:
                decisions.append(Decision(a, 'email_now', 'P1: needs a decision today and is new or escalated'))
                sent_today += 1
        elif a.tier == P2:
            decisions.append(Decision(a, 'digest', 'P2: batched into the 07:00 briefing or the 14:00 digest' + (' (quiet hours)' if quiet else '')))
        else:
            decisions.append(Decision(a, 'briefing_only', 'P3: watch item; briefing and app only'))
    return decisions


def digest_due(now: datetime, last_digest_at: datetime | None) -> bool:
    """A P2 digest goes out at the first tick after each DIGEST_HOURS slot, once per slot."""
    slot = max((h for h in DIGEST_HOURS if now.hour >= h), default=None)
    if slot is None:
        return False
    slot_start = now.replace(hour=slot, minute=0, second=0, microsecond=0)
    return last_digest_at is None or last_digest_at < slot_start


def render_email(decisions: list[Decision], now: datetime, manager_name: str = 'Manager') -> dict:
    """One email for the given decisions: three lines first, then the detail, then why it was sent and how to mute it."""
    immediate = [d for d in decisions if d.channel == 'email_now']
    items = immediate or [d for d in decisions if d.channel == 'digest']
    if not items:
        return {}
    lead = items[0].alert
    subject = f"[ThreadPilot {lead.tier}] {lead.title}" if len(items) == 1 else f"[ThreadPilot {'P1' if immediate else 'digest'}] {len(items)} items need you: {lead.title}"
    lines = [f'Hello {manager_name},', '']
    for d in items[:3]:
        lines.append(f'- {d.alert.title}. {d.alert.action}')
    if len(items) > 3:
        lines.append(f'- and {len(items) - 3} more below.')
    lines += ['', 'Details']
    if immediate:
        for d in items:
            lines += [f'{d.alert.tier} {d.alert.title}', f'  {d.alert.detail}', f'  Rule: {d.alert.rule}', '']
    else:
        # A digest groups by kind: one line per kind with its count, then the top three of each by score.
        kinds: dict[str, list[Decision]] = {}
        for d in items:
            kinds.setdefault(d.alert.kind, []).append(d)
        for kind, group in kinds.items():
            lines.append(f"{kind.replace('_', ' ').title()}: {len(group)}")
            for d in group[:3]:
                lines.append(f'  - {d.alert.title} ({d.alert.detail})')
            if len(group) > 3:
                lines.append(f'  - and {len(group) - 3} more in the app')
            lines.append('')
    lines += [f'Why you got this: {items[0].reason}.',
              'Mute: reply "mute <kind> 7d" or use Settings > Alerts. Nothing in this email was sent to anyone else.',
              f'Business date {now.date().isoformat()} · ThreadPilot']
    return {'subject': subject, 'body': '\n'.join(lines), 'keys': [d.alert.key for d in items]}


def summarize(decisions: list[Decision]) -> dict:
    return {'email_now': [d.alert.as_dict() | {'reason': d.reason} for d in decisions if d.channel == 'email_now'],
            'digest': [d.alert.as_dict() | {'reason': d.reason} for d in decisions if d.channel == 'digest'],
            'briefing_only': [d.alert.as_dict() | {'reason': d.reason} for d in decisions if d.channel == 'briefing_only'],
            'suppressed': [d.alert.as_dict() | {'reason': d.reason} for d in decisions if d.channel == 'suppressed'],
            'policy': {'tiers': {P1: 'email at once', P2: 'digest at 07:00 / 14:00', P3: 'briefing and app only'},
                       'cooldown_hours': COOLDOWN_HOURS, 'escalation_step': ESCALATION_STEP, 'max_p1_per_day': MAX_P1_PER_DAY,
                       'quiet_hours': QUIET_HOURS, 'digest_hours': DIGEST_HOURS}}
