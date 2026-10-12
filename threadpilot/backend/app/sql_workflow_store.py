"""Durable workflow state for stateless HTTP functions (MySQL; SQLite in tests)."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json

import httpx
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import insert as mysql_insert, LONGTEXT
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db.base import Base
from .schemas import DialogState


def table(name, *columns, **kwargs):
    return sa.Table('workflow_' + name, Base.metadata, *columns, **kwargs)


def col(name, length=64, **kwargs):
    return sa.Column(name, sa.String(length), **kwargs)


large_text = sa.Text().with_variant(LONGTEXT(), 'mysql')
sessions = table('sessions', col('id', primary_key=True), sa.Column('state', large_text, nullable=False))
actions = table('actions', col('id', primary_key=True), col('session_id', nullable=False),
                col('kind', nullable=False), col('order_id', nullable=False),
                sa.Column('payload', large_text, nullable=False), col('status', nullable=False),
                col('created_at', nullable=False), sa.Column('receipt', large_text))
reminders = table('reminders', col('id', primary_key=True), col('session_id', nullable=False),
                  col('order_id', nullable=False), col('condition', nullable=False),
                  col('deadline', nullable=False), col('since', nullable=False),
                  sa.Column('evaluated', sa.Integer, nullable=False),
                  sa.UniqueConstraint('session_id', 'order_id', 'condition', name='uq_workflow_reminder'))
replies = table('replies', col('event_id', 100, primary_key=True), col('order_id', nullable=False), col('received_at', nullable=False))
notifications = table('notifications', col('id', 160, primary_key=True), col('session_id', nullable=False),
                      col('order_id', nullable=False), sa.Column('message', sa.Text, nullable=False), col('created_at', nullable=False))
sql_sessions = table('sql_sessions', col('id', primary_key=True), sa.Column('history', large_text, nullable=False))


class WorkflowBusy(Exception):
    pass


class SQLWorkflowStore:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def turn_lock(self, key):
        """Serialize a session across instances; fail fast instead of blocking the event loop."""
        if self.engine.dialect.name != 'mysql':
            yield
            return
        name = hashlib.sha256((str(self.engine.url.database) + ':' + key).encode()).hexdigest()
        with self.engine.connect() as connection:
            acquired = connection.execute(sa.text('SELECT GET_LOCK(:name, 0)'), {'name': name}).scalar()
            if acquired != 1:
                raise WorkflowBusy('Session is busy; retry this request.')
            try:
                yield
            finally:
                try:
                    connection.execute(sa.text('SELECT RELEASE_LOCK(:name)'), {'name': name})
                except Exception:
                    connection.invalidate()
                    raise

    def upsert(self, connection, target, values, updates=None):
        if connection.dialect.name == 'mysql':
            stmt = mysql_insert(target).values(**values)
            changes = {key: stmt.inserted[key] for key in (updates or [])}
            if not changes:
                key = next(iter(target.primary_key.columns)).name
                changes = {key: target.c[key]}
            stmt = stmt.on_duplicate_key_update(**changes)
        else:
            stmt = sqlite_insert(target).values(**values)
            stmt = stmt.on_conflict_do_update(set_={key: stmt.excluded[key] for key in updates}) if updates else stmt.on_conflict_do_nothing()
        connection.execute(stmt)

    def load(self, session_id):
        with self.engine.connect() as db:
            value = db.execute(sa.select(sessions.c.state).where(sessions.c.id == session_id)).scalar_one_or_none()
        if value is None:
            raise KeyError('Unknown session')
        return DialogState.model_validate_json(value)

    def save(self, state):
        with self.engine.begin() as db:
            self.upsert(db, sessions, {'id': state.session_id, 'state': state.model_dump_json()}, ['state'])

    def load_history(self, session_id):
        with self.engine.connect() as db:
            value = db.execute(sa.select(sql_sessions.c.history).where(sql_sessions.c.id == session_id)).scalar_one_or_none()
        if value is None:
            raise KeyError('Unknown SQL session')
        return json.loads(value)

    def save_history(self, session_id, history):
        with self.engine.begin() as db:
            self.upsert(db, sql_sessions, {'id': session_id, 'history': json.dumps(history)}, ['history'])

    def action_result(self, action_id, session_id):
        with self.engine.connect() as db:
            row = db.execute(sa.select(actions).where(actions.c.id == action_id, actions.c.session_id == session_id)).mappings().first()
            return dict(row) if row else None

    @staticmethod
    def action_values(action, session_id, now, status):
        return dict(id=action.id, session_id=session_id, kind=action.kind, order_id=action.order_id,
                    payload=json.dumps(action.payload), status=status, created_at=now.isoformat(), receipt=None)

    def commit_local(self, action, session_id, now):
        with self.engine.begin() as db:
            row = db.execute(sa.select(actions).where(actions.c.id == action.id)).mappings().first()
            if row:
                if row['session_id'] != session_id:
                    raise ValueError('Action belongs to another session')
                return dict(row)
            db.execute(actions.insert().values(**self.action_values(action, session_id, now, 'saved')))
            if action.kind == 'reminder':
                self.upsert(db, reminders, dict(id=action.id, session_id=session_id, order_id=action.order_id,
                    condition=action.payload['condition'], deadline=action.payload['deadline'],
                    since=action.payload['since'], evaluated=0), ['deadline', 'evaluated'])
        return dict(id=action.id, status='saved', kind=action.kind, order_id=action.order_id)

    async def send(self, action, session_id, now, sender):
        previous = self.action_result(action.id, session_id)
        if previous and previous['status'] == 'sent':
            return previous
        if sender is None:
            return {'status': 'not_sent', 'reason': 'Delivery connector is not configured. Draft remains unsent.'}
        with self.engine.begin() as db:
            self.upsert(db, actions, self.action_values(action, session_id, now, 'pending'))
        try:
            receipt = await sender.send({**action.payload, 'order_id': action.order_id}, action.id)
        except (httpx.HTTPError, ValueError, OSError):
            return {'status': 'unknown', 'reason': 'Delivery not confirmed; retry with the same confirmation ID.'}
        with self.engine.begin() as db:
            db.execute(actions.update().where(actions.c.id == action.id).values(status='sent', receipt=receipt, created_at=now.isoformat()))
        return {'status': 'sent', 'receipt': receipt, 'id': action.id}

    def get_reminder(self, session_id, order_id, condition):
        with self.engine.connect() as db:
            row = db.execute(sa.select(reminders).where(reminders.c.session_id == session_id,
                reminders.c.order_id == order_id, reminders.c.condition == condition)).mappings().first()
            return dict(row) if row else None

    def record_reply(self, event_id, order_id, received_at):
        if received_at.tzinfo is None:
            raise ValueError('Timezone is required')
        with self.engine.begin() as db:
            self.upsert(db, replies, dict(event_id=event_id, order_id=order_id, received_at=received_at.isoformat()))

    def evaluate_reminders(self, now, tools):
        with self.turn_lock('reminder-scheduler'), self.engine.begin() as db:
            rows = db.execute(sa.select(reminders).where(reminders.c.evaluated == 0).with_for_update()).mappings().all()
            for row in rows:
                deadline = datetime.fromisoformat(row['deadline'])
                if deadline > now:
                    continue
                order = tools.refresh_order(row['order_id']).record
                since = datetime.fromisoformat(row['since'])
                if row['condition'] == 'no_reply':
                    times = db.execute(sa.select(replies.c.received_at).where(replies.c.order_id == row['order_id'])).scalars()
                    satisfied = any(since <= datetime.fromisoformat(value) <= deadline for value in times)
                else:
                    activity_date = datetime.fromisoformat(order['last_activity_date']).date()
                    satisfied = since.date() < activity_date <= deadline.date()
                if not satisfied:
                    self.upsert(db, notifications, dict(id=f"{row['id']}:{row['deadline']}",
                        session_id=row['session_id'], order_id=row['order_id'],
                        message=f"{row['condition']} condition unmet at {row['deadline']}; based on recorded data only.",
                        created_at=now.isoformat()))
                db.execute(reminders.update().where(reminders.c.id == row['id']).values(evaluated=1))

    def notifications(self, session_id):
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(sa.select(notifications).where(
                notifications.c.session_id == session_id).order_by(notifications.c.created_at)).mappings()]
