"""Persist editable email drafts grounded in an archived morning briefing, who they go to, and when they were sent."""
import json
import re
from datetime import datetime

import sqlalchemy as sa
from .dashboard_store import briefings
from .services.dashboard_service import LOCAL
from .sql_workflow_store import SQLWorkflowStore

metadata = sa.MetaData()
drafts = sa.Table('briefing_email_drafts', metadata,
    sa.Column('briefing_day', sa.String(10), primary_key=True),
    sa.Column('subject', sa.String(240), nullable=False),
    sa.Column('body', sa.Text, nullable=False),
    sa.Column('source_payload', sa.Text, nullable=False),
    sa.Column('version', sa.Integer, nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('updated_at', sa.String(40), nullable=False))

# Kept apart from the draft so the draft's table never has to change. One row per briefing day: who the email is for,
# and the last time it was sent. The email itself is sent from the manager's own mailbox (see frontend/outlook.js);
# the server only records that it happened.
deliveries = sa.Table('briefing_email_deliveries', metadata,
    sa.Column('briefing_day', sa.String(10), primary_key=True),
    sa.Column('to_addresses', sa.Text, nullable=False, default=''),
    sa.Column('cc_addresses', sa.Text, nullable=False, default=''),
    sa.Column('sent_at', sa.String(40)),
    sa.Column('sent_by', sa.String(254)),
    sa.Column('sent_version', sa.Integer),
    sa.Column('send_count', sa.Integer, nullable=False, default=0),
    sa.Column('updated_at', sa.String(40), nullable=False))

ADDRESS = re.compile(r"^[^@\s,;<>\"()]+@[^@\s,;<>\"()]+\.[^@\s,;<>\"()]+$")
MAX_RECIPIENTS = 20


def addresses(values):
    """Normalise a list of email addresses: trimmed, lower-case duplicates dropped, order kept. Raises ValueError."""
    seen, out = set(), []
    for value in values or []:
        value = (value or '').strip()
        if not value:
            continue
        if len(value) > 254 or not ADDRESS.match(value):
            raise ValueError(f'"{value}" is not an email address.')
        if value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)
    if len(out) > MAX_RECIPIENTS:
        raise ValueError(f'At most {MAX_RECIPIENTS} recipients.')
    return out


def split(text):
    return [a for a in (text or '').split(',') if a]


def default_recipients():
    from .config import Settings
    try:
        return addresses(split(Settings().briefing_email_to))
    except ValueError:
        return []


def public(row, delivery=None, fallback_to=()):
    out = {k: row[k] for k in ('briefing_day', 'subject', 'body', 'version', 'created_at', 'updated_at')}
    out['to'] = split(delivery['to_addresses']) if delivery else list(fallback_to)
    out['cc'] = split(delivery['cc_addresses']) if delivery else []
    out['sent'] = ({'at': delivery['sent_at'], 'by': delivery['sent_by'], 'version': delivery['sent_version'],
                    'count': delivery['send_count']} if delivery and delivery['sent_at'] else None)
    return out


class DeliveryTableMissing(RuntimeError):
    """Migration 0006 has not been run on this database yet (on CloudBase migrations are run by hand)."""


def _deliveries(db, work):
    """Run work(db) against briefing_email_deliveries inside a savepoint. If the table does not exist yet, raise
    DeliveryTableMissing and leave the surrounding transaction (the draft itself) untouched."""
    try:
        with db.begin_nested():
            return work(db)
    except sa.exc.DBAPIError as error:
        if sa.inspect(db).has_table(deliveries.name):
            raise
        raise DeliveryTableMissing('Run database migration 0006 (briefing_email_deliveries).') from error


def _read(db, day):
    row = db.execute(sa.select(drafts).where(drafts.c.briefing_day == day)).mappings().first()
    if row is None:
        return None

    def lookup(db):
        delivery = db.execute(sa.select(deliveries).where(deliveries.c.briefing_day == day)).mappings().first()
        last = None
        if delivery is None:
            # Yesterday's list is today's best guess, so the manager types recipients once, not every morning.
            last = db.execute(sa.select(deliveries.c.to_addresses).where(deliveries.c.to_addresses != '')
                              .order_by(deliveries.c.briefing_day.desc()).limit(1)).scalar()
        return delivery, last

    try:
        delivery, last = _deliveries(db, lookup)
    except DeliveryTableMissing:
        delivery, last = None, None      # the draft still opens; recipients start from BRIEFING_EMAIL_TO
    return public(row, delivery, () if delivery else (split(last) if last else default_recipients()))


def _store(db, day, values):
    stamp = datetime.now(LOCAL).isoformat()
    current = db.execute(sa.select(deliveries).where(deliveries.c.briefing_day == day)).mappings().first()
    if current is None:
        db.execute(deliveries.insert().values({'to_addresses': '', 'cc_addresses': '', 'send_count': 0, **values,
                                               'briefing_day': day, 'updated_at': stamp}))
    else:
        db.execute(deliveries.update().where(deliveries.c.briefing_day == day).values(updated_at=stamp, **values))


def generate(database, day):
    with database.engine.begin() as db:
        existing = _read(db, day)
        if existing:
            return existing
        report = db.execute(sa.select(briefings).where(briefings.c.day == day)).mappings().first()
        if not report:
            raise KeyError(day)
        source = {**dict(report), 'payload': json.loads(report['payload'])}
        p = source['payload']
        lines = ['Hello team,', '', f"Morning summary — {day}",
                 f"Business date: {report['business_date']}", '', 'Production',
                 p['yesterday'], p.get('production_note') or '', '', 'Priority issue',
                 p['top_issue'], '', 'Decisions needed', p['decide']]
        if p.get('advice'):
            lines += ['', 'Recommended next steps']
            lines += [f"{i}. {a['title']}: {a['text']}" for i, a in enumerate(p['advice'][:3], 1)]
        if p.get('cleared'):
            lines += ['', 'Handled items'] + ['- ' + title for title in p['cleared']]
        lines += ['', 'Best regards,', 'ThreadPilot']
        stamp = datetime.now(LOCAL).isoformat()
        values = dict(briefing_day=day, subject=f'ThreadPilot morning summary | {day}',
                      body='\n'.join(lines), source_payload=json.dumps(source, ensure_ascii=False),
                      version=1, created_at=stamp, updated_at=stamp)
        SQLWorkflowStore(database.engine).upsert(db, drafts, values)
        return _read(db, day)


def save(database, day, subject, body, version, to=None, cc=None):
    """Save an edited draft. to/cc of None leave the recipients as they are."""
    with database.engine.begin() as db:
        result = db.execute(drafts.update().where(drafts.c.briefing_day == day, drafts.c.version == version)
                            .values(subject=subject, body=body, version=version+1,
                                    updated_at=datetime.now(LOCAL).isoformat()))
        if result.rowcount != 1:
            return None
        if to is not None or cc is not None:
            changes = {}
            if to is not None:
                changes['to_addresses'] = ','.join(to)
            if cc is not None:
                changes['cc_addresses'] = ','.join(cc)
            try:
                _deliveries(db, lambda db: _store(db, day, changes))
            except DeliveryTableMissing:
                pass                          # the text is saved; recipients are kept once the migration has run
        return _read(db, day)


def record_sent(database, day, version, to, cc, sent_by):
    """Record that the manager's mailbox accepted the email. Returns None if there is no draft for that day.
    Raises DeliveryTableMissing if migration 0006 has not been run."""
    with database.engine.begin() as db:
        if db.execute(sa.select(drafts.c.version).where(drafts.c.briefing_day == day)).scalar() is None:
            return None

        def store(db):
            count = db.execute(sa.select(deliveries.c.send_count).where(deliveries.c.briefing_day == day)).scalar() or 0
            _store(db, day, {'to_addresses': ','.join(to), 'cc_addresses': ','.join(cc),
                             'sent_at': datetime.now(LOCAL).isoformat(), 'sent_by': sent_by, 'sent_version': version,
                             'send_count': count + 1})
        _deliveries(db, store)
        return _read(db, day)
