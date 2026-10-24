"""One database snapshot, calendar and capacity model for risk and dispatch decisions."""
from ..business_clock import BusinessClock
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from uuid import uuid4

import sqlalchemy as sa
from ..crud.data_record import MODELS, fields, lock_writes
from ..models.data_record import SyncLock
from ..scheduling_store import schedule, reviews, drafts
from .queue_engine import project, assess_risk, STAGES, QueueAnalysis, ASSUMPTIONS, VERSION, fingerprint  # noqa: F401 (re-exported)
from .queue_workdays import is_working, prev_working, working_days_between, working_days_inclusive, kth_working_day

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


class SchedulingService:
    def __init__(self, database):
        self.database = database

    def preview(self, oid, today):
        with self.database.sessions.begin() as session:
            data = read_locked(session, today)
            result = QueueAnalysis(data).expedite(oid)
            rid, stamp = str(uuid4()), BusinessClock().now().isoformat()
            session.execute(reviews.insert().values(id=rid, order_id=oid, fingerprint=fingerprint(data),
                            payload=json.dumps(result), created_at=stamp, status='preview'))
        return {**result, 'review_id': rid, 'created_at': stamp}

    def decide(self, rid, decision, reviewer, note, today, draft_id=None, draft_version=None):
        with self.database.sessions.begin() as session:
            data = read_locked(session, today)
            row = session.execute(sa.select(reviews).where(reviews.c.id == rid)).mappings().first()
            if row is None:
                raise KeyError('Review not found.')
            if row['status'] != 'preview':
                if row['decision'] != decision or row['reviewed_by'] != reviewer or row['note'] != note:
                    raise ValueError('This review already has a different decision.')
                return {'review_id': rid, 'status': row['status'], 'decision': decision, 'replayed': True}
            if fingerprint(data) != row['fingerprint'] or not timedelta(0) <= BusinessClock().now() - datetime.fromisoformat(row['created_at']) <= timedelta(minutes=15):
                raise ValueError('Data, date or schedule changed, or the preview expired. Generate and review a fresh analysis.')
            linked = session.execute(sa.select(drafts.c.id).where(drafts.c.review_id == rid)).scalar()
            if linked and not draft_id:
                raise ValueError('Submit this review with its saved draft ID and version.')
            if draft_id:
                draft = session.execute(sa.select(drafts).where(drafts.c.id == draft_id)).mappings().first()
                if not draft or draft['review_id'] != rid or draft['version'] != draft_version or draft['status'] != 'open':
                    raise ValueError('Draft version changed. Reload and review before submitting.')
                content = json.loads(draft['content'])
                if content['text'].strip() != note or content['reviewer'].strip() != reviewer or content['decision'] != decision:
                    raise ValueError('The submitted decision must match the saved form draft.')
                session.execute(drafts.update().where(drafts.c.id == draft_id).values(status='submitted', version=draft_version+1))
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
                            reviewed_by=reviewer, note=note, decided_at=BusinessClock().now().isoformat()))
        return {'review_id': rid, 'status': status, 'decision': decision, 'replayed': False}

    def history(self):
        with self.database.sessions() as session:
            rows = session.execute(sa.select(reviews).where(reviews.c.status != 'preview')
                                   .order_by(reviews.c.decided_at.desc()).limit(100)).mappings().all()
            return [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]
