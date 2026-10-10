"""Persist editable email drafts grounded in an archived morning briefing."""
import json
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


def public(row):
    return {k: row[k] for k in ('briefing_day', 'subject', 'body', 'version', 'created_at', 'updated_at')}


def generate(database, day):
    with database.engine.begin() as db:
        existing = db.execute(sa.select(drafts).where(drafts.c.briefing_day == day)).mappings().first()
        if existing:
            return public(existing)
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
        return public(db.execute(sa.select(drafts).where(drafts.c.briefing_day == day)).mappings().one())


def save(database, day, subject, body, version):
    with database.engine.begin() as db:
        result = db.execute(drafts.update().where(drafts.c.briefing_day == day, drafts.c.version == version)
                            .values(subject=subject, body=body, version=version+1,
                                    updated_at=datetime.now(LOCAL).isoformat()))
        if result.rowcount != 1:
            return None
        return public(db.execute(sa.select(drafts).where(drafts.c.briefing_day == day)).mappings().one())
