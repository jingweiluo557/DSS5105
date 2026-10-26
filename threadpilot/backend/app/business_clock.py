"""A persisted clock offset; seconds continue to pass at normal speed."""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from contextlib import contextmanager
from .config import Settings

LOCAL = timezone(timedelta(hours=8))


class BusinessClock:
    def __init__(self, settings=None):
        self.settings = settings or Settings()

    def read(self):
        if self.settings.workflow_storage == 'database':
            from .cloud_state import read_clock
            payload = read_clock(self.settings)
            return json.loads(payload) if payload else None
        path = self.settings.business_clock_store
        if not path.exists():
            return None
        with sqlite3.connect(path, timeout=10) as db:
            db.execute('CREATE TABLE IF NOT EXISTS clock (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            row = db.execute('SELECT payload FROM clock WHERE id=1').fetchone()
            return json.loads(row[0]) if row else None

    def now(self, real=None):
        real = real or datetime.now(LOCAL)
        state = self.read()
        if state:
            return real if state['mode'] == 'live' else real + timedelta(seconds=state['offset'])
        value = os.getenv('BUSINESS_NOW', self.settings.business_now)
        result = real if value == 'live' else datetime.fromisoformat(value)
        if result.tzinfo is None:
            raise ValueError('BUSINESS_NOW must include timezone')
        return result

    def status(self):
        state = self.read()
        return {**(state or {'mode':'legacy','run_id':'','version':0}),
                'now':self.now().isoformat(), 'timezone':'Asia/Shanghai'}

    @contextmanager
    def transaction(self):
        if self.settings.workflow_storage == 'database':
            from .cloud_state import shared_store
            with shared_store(self.settings, 'clock') as db:
                yield db
            return
        path = self.settings.business_clock_store
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=10) as db:
            db.execute('CREATE TABLE IF NOT EXISTS clock (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            yield db

    def save(self, mode, target, version, real=None):
        real = real or datetime.now(LOCAL)
        now = real if mode == 'live' else target.astimezone(LOCAL)
        with self.transaction() as db:
            row = db.execute('SELECT payload FROM clock WHERE id=1').fetchone()
            old = json.loads(row[0]) if row else {'version':0}
            if old['version'] != version:
                from fastapi import HTTPException
                raise HTTPException(409, 'Clock changed. Reload before saving.')
            state = {'mode':mode, 'offset':(now-real).total_seconds(), 'version':version+1,
                     'run_id':str(uuid4()) if mode == 'demo' else '', 'set_at':real.isoformat(),
                     'schedule_start_day':(now.date()+timedelta(days=int(now.hour>=7))).isoformat()}
            db.execute('INSERT OR REPLACE INTO clock VALUES (1,?)',(json.dumps(state),))
        return self.status()
