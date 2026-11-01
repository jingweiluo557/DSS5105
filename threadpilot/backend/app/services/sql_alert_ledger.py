"""Durable alert ledger. Schema is managed by Alembic, never at startup."""
import json
from datetime import datetime
from uuid import uuid4
import sqlalchemy as sa
from ..db.base import Base
from ..cloud_state import engine_for, large
from ..sql_workflow_store import SQLWorkflowStore


def col(name, length=64, **kw):
    return sa.Column(name, sa.String(length), **kw)


decisions = sa.Table('alert_decisions', Base.metadata,
    col('id', primary_key=True), col('key', 160), col('kind'), col('tier', 16),
    sa.Column('score', sa.Integer), col('channel'), sa.Column('reason', sa.Text),
    col('sent_at'), col('business_date', 10), sa.Column('payload', large),
    col('email_id'), col('email_status'))
shelves = sa.Table('alert_shelves', Base.metadata,
    col('target', 160, primary_key=True), col('until'), col('set_by', 100), col('set_at'))
digests = sa.Table('alert_digests', Base.metadata,
    col('id', primary_key=True), col('sent_at'), col('business_date', 10),
    sa.Column('keys', large), col('email_status'))
feedback = sa.Table('alert_feedback', Base.metadata,
    col('id', primary_key=True), col('key', 160), sa.Column('useful', sa.Integer),
    col('note', 300), col('at'))


class SQLAlertLedger:
    def __init__(self, settings):
        self.engine = engine_for(settings.database_url.get_secret_value())

    def history(self, days=30):
        with self.engine.connect() as db:
            rows = db.execute(sa.select(decisions.c.key, decisions.c.tier, decisions.c.score,
                decisions.c.channel, decisions.c.sent_at).order_by(decisions.c.sent_at.desc()).limit(5000)).mappings().all()
        return [dict(r) for r in reversed(rows)]

    def shelved(self):
        with self.engine.connect() as db:
            return dict(db.execute(sa.select(shelves.c.target, shelves.c.until)).all())

    def shelve(self, target, until, set_by, now):
        with self.engine.begin() as db:
            SQLWorkflowStore(self.engine).upsert(db, shelves,
                dict(target=target, until=until, set_by=set_by, set_at=now.isoformat()),
                ['until', 'set_by', 'set_at'])

    def last_digest(self):
        with self.engine.connect() as db:
            value = db.scalar(sa.select(sa.func.max(digests.c.sent_at)))
        return datetime.fromisoformat(value) if value else None

    def record(self, items, now, email_id=None, email_status=None, channels=('email_now', 'digest')):
        rows = [dict(id=str(uuid4()), key=d.alert.key, kind=d.alert.kind, tier=d.alert.tier,
            score=d.alert.score, channel=d.channel, reason=d.reason, sent_at=now.isoformat(),
            business_date=now.date().isoformat(), payload=json.dumps(d.alert.as_dict(), ensure_ascii=False),
            email_id=email_id, email_status=email_status) for d in items if d.channel in channels]
        if rows:
            with self.engine.begin() as db:
                db.execute(decisions.insert(), rows)

    def record_digest(self, now, keys, status):
        with self.engine.begin() as db:
            db.execute(digests.insert().values(id=str(uuid4()), sent_at=now.isoformat(),
                business_date=now.date().isoformat(), keys=json.dumps(keys), email_status=status))

    def feedback(self, key, useful, note, now):
        with self.engine.begin() as db:
            db.execute(feedback.insert().values(id=str(uuid4()), key=key, useful=int(useful), note=note[:300], at=now.isoformat()))

    def kpis(self, now):
        week = datetime.fromordinal(now.date().toordinal() - 7).isoformat()
        def count_since(since):
            return sa.select(sa.func.count(sa.distinct(decisions.c.email_id))).where(
                decisions.c.channel == 'email_now', decisions.c.sent_at >= since)
        with self.engine.connect() as db:
            today = db.scalar(count_since(now.date().isoformat()))
            weekly = db.scalar(count_since(week))
            batches = db.execute(sa.select(digests.c['keys']).where(digests.c.sent_at >= week)).scalars().all()
            count, useful = db.execute(sa.select(sa.func.count(), sa.func.sum(feedback.c.useful)).select_from(feedback)).one()
        return {'p1_emails_today': today, 'p1_emails_last_7_days': weekly,
            'digests_last_7_days': len(batches), 'avg_items_per_digest': round(sum(len(json.loads(x)) for x in batches) / len(batches), 1) if batches else 0,
            'feedback_count': count, 'rated_useful_pct': round(100 * (useful or 0) / count, 1) if count else None,
            'targets': {'p1_emails_per_week': '<= 5', 'rated_useful_pct': '>= 70', 'note': 'alarm-management practice: few, actionable, never repeated'}}
