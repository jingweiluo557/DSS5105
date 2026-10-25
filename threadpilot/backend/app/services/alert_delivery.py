"""Alert delivery: evaluate the policy on the current snapshot, record every decision, and (only when enabled) send
P1 emails and P2 digests to the manager through the connected Outlook account.

Default is dry run (ALERT_EMAILS_ENABLED=false): decisions are recorded in the ledger and visible in the app and in
GET /api/alerts/preview, but nothing leaves the system. The same minute timer that runs the briefing calls run().
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..business_clock import BusinessClock
from . import alert_policy
from .email_settings import EmailSettings
from .outlook_service import OutlookService


class AlertLedger:
    """SQLite ledger of decisions, shelves and digest timestamps (same storage style as workflow_store)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS alert_decisions (id TEXT PRIMARY KEY, key TEXT, kind TEXT, tier TEXT, score INTEGER,
                    channel TEXT, reason TEXT, sent_at TEXT, business_date TEXT, payload TEXT, email_id TEXT, email_status TEXT);
                CREATE TABLE IF NOT EXISTS alert_shelves (target TEXT PRIMARY KEY, until TEXT, set_by TEXT, set_at TEXT);
                CREATE TABLE IF NOT EXISTS alert_digests (sent_at TEXT, business_date TEXT, keys TEXT, email_status TEXT);
                CREATE TABLE IF NOT EXISTS alert_feedback (key TEXT, useful INTEGER, note TEXT, at TEXT);''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def history(self, days: int = 30) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('SELECT key, tier, score, channel, sent_at FROM alert_decisions ORDER BY sent_at').fetchall()
        return [{'key': k, 'tier': t, 'score': s, 'channel': c, 'sent_at': a} for k, t, s, c, a in rows][-5000:]

    def shelved(self) -> dict[str, str]:
        with self.connect() as db:
            return dict(db.execute('SELECT target, until FROM alert_shelves').fetchall())

    def shelve(self, target: str, until: str, set_by: str, now: datetime) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO alert_shelves VALUES (?,?,?,?)', (target, until, set_by, now.isoformat()))

    def last_digest(self) -> datetime | None:
        with self.connect() as db:
            row = db.execute('SELECT MAX(sent_at) FROM alert_digests').fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    def record(self, decisions, now: datetime, email_id: str | None = None, email_status: str | None = None, channels=('email_now', 'digest')) -> None:
        with self.connect() as db:
            for d in decisions:
                if d.channel in channels:
                    db.execute('INSERT INTO alert_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                               (str(uuid4()), d.alert.key, d.alert.kind, d.alert.tier, d.alert.score, d.channel, d.reason, now.isoformat(),
                                now.date().isoformat(), json.dumps(d.alert.as_dict(), ensure_ascii=False), email_id, email_status))

    def record_digest(self, now: datetime, keys: list[str], status: str) -> None:
        with self.connect() as db:
            db.execute('INSERT INTO alert_digests VALUES (?,?,?,?)', (now.isoformat(), now.date().isoformat(), json.dumps(keys), status))

    def feedback(self, key: str, useful: bool, note: str, now: datetime) -> None:
        with self.connect() as db:
            db.execute('INSERT INTO alert_feedback VALUES (?,?,?,?)', (key, int(useful), note[:300], now.isoformat()))

    def kpis(self, now: datetime) -> dict:
        """Alarm-management KPIs: interruptions per week, items per digest, usefulness as rated by the manager."""
        with self.connect() as db:
            emails = db.execute("SELECT COUNT(DISTINCT email_id) FROM alert_decisions WHERE channel='email_now' AND sent_at >= ?", ((now.replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()[:10],)).fetchone()[0]
            week = (now.date().toordinal() - 7)
            weekly = db.execute("SELECT COUNT(DISTINCT email_id) FROM alert_decisions WHERE channel='email_now' AND email_id IS NOT NULL AND sent_at >= ?", (datetime.fromordinal(week).isoformat(),)).fetchone()[0]
            digests = db.execute('SELECT COUNT(*), AVG(json_array_length(keys)) FROM alert_digests WHERE sent_at >= ?', (datetime.fromordinal(week).isoformat(),)).fetchone()
            fb = db.execute('SELECT COUNT(*), SUM(useful) FROM alert_feedback').fetchone()
        return {'p1_emails_today': emails, 'p1_emails_last_7_days': weekly, 'digests_last_7_days': digests[0], 'avg_items_per_digest': round(digests[1] or 0, 1),
                'feedback_count': fb[0], 'rated_useful_pct': round(100 * (fb[1] or 0) / fb[0], 1) if fb[0] else None,
                'targets': {'p1_emails_per_week': '<= 5', 'rated_useful_pct': '>= 70', 'note': 'alarm-management practice: few, actionable, never repeated'}}


class AlertDelivery:
    def __init__(self, settings, ledger_path: Path | None = None) -> None:
        self.settings = settings
        self.outlook = OutlookService(settings)
        self.preferences = EmailSettings(settings)
        self.ledger = AlertLedger(ledger_path or settings.workflow_db.with_name('alerts.sqlite3'))

    def evaluate(self, data: dict, now: datetime) -> list[alert_policy.Decision]:
        return alert_policy.gate(alert_policy.detect(data, now), self.ledger.history(), now, self.ledger.shelved())

    async def run(self, snapshot_loader, now: datetime | None = None, send: bool | None = None) -> dict:
        """One scheduler tick. snapshot_loader() -> the queue snapshot dict; send defaults to the ALERT_EMAILS_ENABLED flag."""
        now = now or BusinessClock(self.settings).now()
        send = getattr(self.settings, 'alert_emails_enabled', False) if send is None else send
        data = await asyncio.to_thread(snapshot_loader)
        decisions = await asyncio.to_thread(self.evaluate, data, now)
        result = {'business_date': now.date().isoformat(), 'send': send, **{k: len(v) for k, v in alert_policy.summarize(decisions).items() if isinstance(v, list)}}
        immediate = [d for d in decisions if d.channel == 'email_now']
        digest = [d for d in decisions if d.channel == 'digest']
        prefs = await asyncio.to_thread(self.preferences.read)
        recipient, name = prefs.get('manager_email'), prefs.get('manager_name', 'Manager')
        if immediate:
            mail = alert_policy.render_email(immediate, now, name)
            status = await self._send(mail, recipient, send)
            email_id = str(uuid4())
            await asyncio.to_thread(self.ledger.record, immediate, now, email_id, status)
            result['p1_email'] = {'subject': mail['subject'], 'status': status, 'keys': mail['keys']}
        if digest and alert_policy.digest_due(now, await asyncio.to_thread(self.ledger.last_digest)):
            mail = alert_policy.render_email(digest, now, name)
            status = await self._send(mail, recipient, send)
            await asyncio.to_thread(self.ledger.record, digest, now, None, status)
            await asyncio.to_thread(self.ledger.record_digest, now, mail['keys'], status)
            result['digest_email'] = {'subject': mail['subject'], 'status': status, 'items': len(mail['keys'])}
        return result

    async def _send(self, mail: dict, recipient: str | None, send: bool) -> str:
        if not send:
            return 'dry_run'
        if not recipient or self.outlook.missing():
            return 'not_configured'
        try:
            outcome = await asyncio.to_thread(self.outlook.send, str(uuid4()), {'to': [recipient], 'subject': mail['subject'], 'body': mail['body']})
            return outcome.get('status', 'unknown')
        except Exception:
            return 'unknown'
