"""One database snapshot, calendar and capacity model for risk and dispatch decisions."""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from uuid import uuid4

import sqlalchemy as sa
from ..crud.data_record import MODELS, fields, lock_writes
from ..models.data_record import SyncLock
from ..scheduling_store import schedule, reviews
from .queue_engine import project, assess_risk, STAGES
from .queue_workdays import is_working, prev_working, working_days_between, working_days_inclusive, kth_working_day

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
    return hashlib.sha256(json.dumps({'algorithm': VERSION, **data}, sort_keys=True, default=str).encode()).hexdigest()


def read_locked(session, today):
    # Share the import/CRUD lock so a preview cannot mix old orders with new output.
    if session.bind.dialect.name == 'sqlite':
        session.execute(sa.update(SyncLock).where(SyncLock.id == 1).values(id=1))
    lock_writes(session)
    data = {'today': today}
    for name in ('orders', 'production_log', 'workshops'):
        data[name] = [{**fields(name, r), '_record_id': r.id, '_version': r.version}
                      for r in session.scalars(sa.select(MODELS[name]).order_by(MODELS[name].id))]
    row = session.execute(sa.select(schedule).where(schedule.c.id == 1)).mappings().first()
    data['schedule'] = {'version': row['version'], 'priority': json.loads(row['priority'])} if row else {'version': 0, 'priority': []}
    return data


def current_snapshot(database, today):
    with database.sessions.begin() as session:
        return read_locked(session, today)


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


class SchedulingService:
    def __init__(self, database):
        self.database = database

    def preview(self, oid, today):
        with self.database.sessions.begin() as session:
            data = read_locked(session, today)
            result = QueueAnalysis(data).expedite(oid)
            rid, stamp = str(uuid4()), datetime.now(timezone.utc).isoformat()
            session.execute(reviews.insert().values(id=rid, order_id=oid, fingerprint=fingerprint(data),
                            payload=json.dumps(result), created_at=stamp, status='preview'))
        return {**result, 'review_id': rid, 'created_at': stamp}

    def decide(self, rid, decision, reviewer, note, today):
        with self.database.sessions.begin() as session:
            data = read_locked(session, today)
            row = session.execute(sa.select(reviews).where(reviews.c.id == rid)).mappings().first()
            if row is None:
                raise KeyError('Review not found.')
            if row['status'] != 'preview':
                if row['decision'] != decision or row['reviewed_by'] != reviewer or row['note'] != note:
                    raise ValueError('This review already has a different decision.')
                return {'review_id': rid, 'status': row['status'], 'decision': decision, 'replayed': True}
            if fingerprint(data) != row['fingerprint'] or datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at']) > timedelta(minutes=15):
                raise ValueError('Data, date or schedule changed, or the preview expired. Generate and review a fresh analysis.')
            payload = json.loads(row['payload'])
            if decision == 'apply':
                if not payload['can_apply']:
                    raise ValueError('This analysis does not support a schedule adjustment; save the advice instead.')
                priority = [row['order_id']] + [i for i in data['schedule']['priority'] if i != row['order_id']
                                               and any(o['order_id'] == i and o['status'] == 'IN_PROGRESS' for o in data['orders'])]
                values = {'version': data['schedule']['version'] + 1, 'priority': json.dumps(priority)}
                if data['schedule']['version']:
                    session.execute(schedule.update().where(schedule.c.id == 1).values(**values))
                else:
                    session.execute(schedule.insert().values(id=1, **values))
            status = 'applied' if decision == 'apply' else 'saved' if decision == 'save' else 'rejected'
            session.execute(reviews.update().where(reviews.c.id == rid).values(status=status, decision=decision,
                            reviewed_by=reviewer, note=note, decided_at=datetime.now(timezone.utc).isoformat()))
        return {'review_id': rid, 'status': status, 'decision': decision, 'replayed': False}

    def history(self):
        with self.database.sessions() as session:
            rows = session.execute(sa.select(reviews).where(reviews.c.status != 'preview')
                                   .order_by(reviews.c.decided_at.desc()).limit(100)).mappings().all()
            return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]
