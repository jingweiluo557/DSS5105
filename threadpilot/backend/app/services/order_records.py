"""Shared order notes, change history and once-only morning briefing watches."""
import json
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..business_clock import BusinessClock, LOCAL
from ..db.base import Base
from ..models.data_record import Order
from ..sql_workflow_store import actions

journal = sa.Table('order_status_journal', Base.metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('order_id', sa.String(32), nullable=False, index=True),
    sa.Column('business_day', sa.String(10), nullable=False),
    sa.Column('event', sa.String(24), nullable=False))


def start_history(db, now):
    """The first partial business day cannot prove a whole day of inactivity."""
    if db.scalar(sa.select(journal.c.id).where(journal.c.id == 'coverage')):
        return
    insert = mysql_insert if db.dialect.name == 'mysql' else sqlite_insert
    stmt = insert(journal).values(id='coverage', order_id='', event='coverage',
                                  business_day=now.astimezone(LOCAL).date().isoformat())
    stmt = (stmt.on_duplicate_key_update(id=journal.c.id) if db.dialect.name == 'mysql'
            else stmt.on_conflict_do_nothing())
    db.execute(stmt)


@sa.event.listens_for(Order, 'after_update')
def record_transition(mapper, db, order):
    attrs = sa.inspect(order).attrs
    if any(attrs[key].history.has_changes() for key in ('status', 'current_stage')):
        write_event(db, order, 'changed')


@sa.event.listens_for(Order, 'after_delete')
def record_deletion(mapper, db, order):
    write_event(db, order, 'deleted')


@sa.event.listens_for(Order, 'after_insert')
def record_creation(mapper, db, order):
    write_event(db, order, 'created')


def write_event(db, order, event):
    now = BusinessClock().now()
    db.execute(journal.insert().values(id=str(uuid4()), order_id=order.order_id,
        business_day=now.astimezone(LOCAL).date().isoformat(), event=event))


class OrderRecords:
    def __init__(self, database):
        self.database = database

    def save(self, action, session_id, now):
        kind = 'briefing_watch' if action.kind == 'reminder' else 'note'
        with self.database.engine.begin() as db:
            if kind == 'briefing_watch':
                start_history(db, now)
            insert = mysql_insert if db.dialect.name == 'mysql' else sqlite_insert
            stmt = insert(actions).values(id=action.id, session_id=session_id, kind=kind,
                order_id=action.order_id, payload=json.dumps(action.payload, ensure_ascii=False),
                status='pending' if kind == 'briefing_watch' else 'saved', created_at=now.isoformat())
            db.execute(stmt.on_duplicate_key_update(id=actions.c.id) if db.dialect.name == 'mysql'
                       else stmt.on_conflict_do_nothing())
            stored = db.execute(sa.select(actions).where(actions.c.id == action.id)).mappings().one()
            if (stored.session_id != session_id or stored.order_id != action.order_id or
                    stored.kind != kind or json.loads(stored.payload) != action.payload):
                raise ValueError('This confirmation was already used for another record.')
        return {'id': action.id, 'status': 'saved', 'kind': kind}

    def confirmed(self, action_id, session_id):
        with self.database.engine.connect() as db:
            return db.scalar(sa.select(actions.c.kind).where(actions.c.id == action_id,
                actions.c.session_id == session_id, actions.c.kind.in_(['note', 'briefing_watch'])))

    def briefing_due(self, now):
        day = now.astimezone(LOCAL)
        if day.hour < 7:
            return False
        with self.database.engine.connect() as db:
            payloads = db.scalars(sa.select(actions.c.payload).where(actions.c.kind == 'briefing_watch',
                actions.c.status.in_(['no_change', 'unverified']), actions.c.receipt.is_(None)))
            return any(json.loads(payload)['report_day'] == day.date().isoformat() for payload in payloads)

    def delete(self, record_id):
        # Keep the confirmation ID so replaying a saved action cannot recreate it.
        with self.database.engine.begin() as db:
            row = db.execute(sa.select(actions.c.status).where(actions.c.id == record_id,
                actions.c.kind.in_(['note', 'briefing_watch'])).with_for_update()).first()
            if row is None:
                return False
            if row.status != 'deleted':
                db.execute(actions.update().where(actions.c.id == record_id).values(status='deleted'))
            return True

    def list(self, order_id=None):
        q = sa.select(actions).where(actions.c.kind.in_(['note', 'briefing_watch']), actions.c.status != 'deleted')
        if order_id:
            q = q.where(actions.c.order_id == order_id)
        with self.database.engine.connect() as db:
            rows = db.execute(q.order_by(actions.c.created_at.desc(), actions.c.id)).mappings()
            return [dict(id=r.id, order_id=r.order_id, kind=r.kind, status=r.status,
                         created_at=r.created_at, **json.loads(r.payload),
                         report_id=r.receipt) for r in rows]

    def evaluate(self, now):
        with self.database.engine.begin() as db:
            start_history(db, now)
            evaluate(db, now.astimezone(LOCAL).date().isoformat())


def evaluate(db, today):
    coverage = db.scalar(sa.select(journal.c.business_day).where(journal.c.id == 'coverage'))
    rows = db.execute(sa.select(actions).where(actions.c.kind == 'briefing_watch',
        actions.c.status == 'pending').with_for_update()).mappings().all()
    for row in rows:
        day = json.loads(row.payload)['observation_day']
        if day >= today:
            continue
        events = set(db.scalars(sa.select(journal.c.event).where(
            journal.c.order_id == row.order_id, journal.c.business_day == day)))
        if 'changed' in events:
            status = 'changed'
        elif not coverage or coverage >= day or events.intersection({'created', 'deleted'}):
            status = 'unverified'
        else:
            status = 'no_change'
        db.execute(actions.update().where(actions.c.id == row.id).values(status=status))


def attach_to_report(db, today, report_id):
    evaluate(db, today)
    rows = db.execute(sa.select(actions).where(actions.c.kind == 'briefing_watch',
        actions.c.status.in_(['no_change', 'unverified'])).order_by(actions.c.id).with_for_update()).mappings().all()
    items = []
    for row in rows:
        payload = json.loads(row.payload)
        if payload['report_day'] != today:
            continue
        finding = ('No recorded status or stage change' if row.status == 'no_change'
                   else 'Incomplete status history; a change could not be verified')
        items.append({'id': row.id, 'order_id': row.order_id, 'result': row.status,
                      'text': f"{row.order_id}: {finding} on {payload['observation_day']}."})
        db.execute(actions.update().where(actions.c.id == row.id).values(receipt=report_id))
    return items
