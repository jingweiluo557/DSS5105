"""Daily durable send claims. No automatic retry after a send has been submitted."""
import asyncio
import logging
import secrets
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL
from fastapi import HTTPException
from .email_settings import EmailSettings
from .dashboard_service import LOCAL
from ..business_clock import BusinessClock


class BriefingDelivery:
    def __init__(self, settings):
        self.preferences = EmailSettings(settings)
        self.outlook = self.preferences.outlook

    def table(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS briefing_deliveries '
                   '(day TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def put(self, db, job):
        db.execute('INSERT OR REPLACE INTO briefing_deliveries VALUES (?,?)',
                   (job.get('storage_key', job['day']), self.outlook.pack(job)))

    def history(self):
        with self.outlook.db() as db:
            self.table(db)
            jobs = [self.outlook.unpack(r[0]) for r in db.execute(
                'SELECT payload FROM briefing_deliveries')]
            jobs = sorted(jobs, key=lambda j:j['created_at'], reverse=True)[:100]
            for job in jobs:
                # Reconcile a process crash after Graph response / before job update.
                if job['status'] == 'sending':
                    row = db.execute('SELECT status FROM sends WHERE id=?', (job['id'],)).fetchone()
                    if row:
                        job['status'] = row[0]
                        job['diagnostic'] = self.outlook.get(db, 'send:' + job['id'])
            return jobs

    def claim(self, now, manual_day=None):
        with self.outlook.db() as db:
            self.table(db)
            prefs = self.preferences.read_in(db)
            day = manual_day.isoformat() if manual_day else now.date().isoformat()
            clock = BusinessClock(self.outlook.settings).read() or {}
            run_id = clock.get('run_id', '') if not manual_day else ''
            start_day = clock.get('schedule_start_day') or prefs['start_day']
            if prefs.get('clock_run_id','') == run_id and prefs.get('start_day'):
                start_day = max(start_day or prefs['start_day'],prefs['start_day'])
            if manual_day is None and (not prefs['briefing_enabled'] or now.hour < 7 or not start_day or day < start_day):
                return None
            key = run_id + ':' + day if run_id else day
            row = db.execute('SELECT payload FROM briefing_deliveries WHERE day=?', (key,)).fetchone()
            job = self.outlook.unpack(row[0]) if row else None
            stamp = now.timestamp()
            if job:
                if job['status'] == 'generating' and job['attempts'] >= 3 and job['retry_at'] <= stamp:
                    job.update(status='generation_failed', updated_at=now.isoformat(),
                               diagnostic={'message': 'Briefing preparation was interrupted. No further automatic attempt today.'})
                    self.put(db, job)
                if job['status'] not in ('generating', 'generation_failed') or job['attempts'] >= 3 or job['retry_at'] > stamp:
                    return None
            else:
                job = {'id': str(uuid5(NAMESPACE_URL, 'threadpilot:morning:' + key)), 'day': day,
                       'storage_key': key, 'clock_run_id':run_id,
                       'sender': (self.outlook.get(db, 'account') or {}).get('username'),
                       'recipient': prefs['manager_email'], 'manager_name': prefs['manager_name'],
                       'subject_prefix': prefs['subject_prefix'], 'attempts': 0,
                       'trigger': 'manual' if manual_day else 'scheduled',
                       'created_at': datetime.now(LOCAL).isoformat(), 'scheduled_at': now.isoformat() if manual_day else day + 'T07:00:00+08:00',
                       'report_id': None, 'subject': None, 'body': None, 'diagnostic': None}
            job.update(status='generating', attempts=job['attempts'] + 1,
                       retry_at=stamp + 900, lease=secrets.token_hex(16), updated_at=now.isoformat())
            self.put(db, job)
            return job

    def update(self, job, **values):
        with self.outlook.db() as db:
            self.table(db)
            row = db.execute('SELECT payload FROM briefing_deliveries WHERE day=?', (job.get('storage_key',job['day']),)).fetchone()
            current = self.outlook.unpack(row[0]) if row else None
            if not current or current['lease'] != job['lease']:
                return False
            if values.get('status') == 'sending':
                prefs = self.preferences.read_in(db)
                clock = BusinessClock(self.outlook.settings).read() or {}
                changed_clock = job.get('trigger') != 'manual' and job.get('clock_run_id','') != clock.get('run_id','')
                if changed_clock or not prefs['briefing_enabled'] or prefs['manager_email'] != job['recipient']:
                    job.update(status='cancelled', diagnostic={'message': 'Schedule or recipient changed during generation.'})
                    self.put(db, job)
                    return False
            job.update(values, updated_at=BusinessClock(self.outlook.settings).now().isoformat())
            self.put(db, job)
            return True

    async def run(self, app, now=None, generate=None, manual_day=None):
        if manual_day is not None and generate is None:
            raise ValueError('Manual delivery requires an explicitly dated report generator.')
        now = (now or BusinessClock(self.outlook.settings).now()).astimezone(LOCAL)
        if self.outlook.missing():
            return {'status': 'not_configured'}
        job = await asyncio.to_thread(self.claim, now, manual_day)
        if not job:
            return {'status': 'not_due_or_claimed'}
        try:
            if generate is None:
                from ..api.morning_api import generate_morning
                generate = lambda: generate_morning(app, scheduled=True)
            result = await generate()
            report = result.get('report')
            if not report or report.get('day') != job['day']:
                raise ValueError('A current-day briefing is required.')
            subject = job['subject_prefix'] + ' | ' + job['day']
            body = '\n\n'.join([f"Hello {job['manager_name'] or 'Manager'},",
                f"Morning briefing — {job['day']}\nBusiness date: {report['business_date']}",
                'Production\n' + report['yesterday'], 'Priorities\n' + report['top_issue'],
                'Next steps\n' + report['decide'], 'Best regards,\nThreadPilot'])
        except Exception:
            await asyncio.to_thread(self.update, job, status='generation_failed',
                retry_at=now.timestamp() + 300,
                diagnostic={'message': 'Current-day briefing generation failed. No email was sent.'})
            return {'status': 'generation_failed'}
        if not await asyncio.to_thread(self.update, job, status='sending', subject=subject, body=body,
                                        report_id=report['id'], business_date=report['business_date']):
            return {'status': 'lease_lost'}
        try:
            result = await asyncio.to_thread(self.outlook.send, job['id'],
                {'to': [job['recipient']], 'subject': subject, 'body': body})
            await asyncio.to_thread(self.update, job, status=result['status'], diagnostic=result.get('diagnostic'))
            return result
        except HTTPException as error:
            await asyncio.to_thread(self.update, job, status='needs_attention',
                                   diagnostic={'message': str(error.detail)[:300]})
            return {'status': 'needs_attention'}
        except Exception:
            # A crash may happen after submission: never retry a new send automatically.
            await asyncio.to_thread(self.update, job, status='unknown',
                                   diagnostic={'message': 'Check Sent Items before any further action.'})
            return {'status': 'unknown'}


async def delivery_loop(app):
    service = BriefingDelivery(app.state.settings)
    while True:
        try:
            await service.run(app)
        except Exception:
            logging.getLogger(__name__).warning('Briefing delivery check failed; will check again.')
        await asyncio.sleep(2)
