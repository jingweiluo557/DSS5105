"""Confirmed customer emails follow the shared business clock and demo run."""
import asyncio
import logging
from datetime import datetime, timedelta
from .outlook_service import OutlookService
from .email_settings import email
from .dashboard_service import LOCAL
from ..business_clock import BusinessClock


class ScheduledEmail:
    def __init__(self, settings):
        self.outlook = OutlookService(settings)

    def table(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS scheduled_emails (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def put(self, db, job):
        db.execute('INSERT OR REPLACE INTO scheduled_emails VALUES (?,?)',(job['id'],self.outlook.pack(job)))

    def claim_now(self, action, now):
        if self.outlook.missing():
            return None, {'status':'not_sent','reason':'Configure and connect Outlook in Settings before sending.'}
        recipient=email(action.payload['recipient'])
        run_id=(BusinessClock(self.outlook.settings).read() or {}).get('run_id','')
        if action.payload.get('clock_run_id',run_id)!=run_id:
            return None, {'status':'not_sent','reason':'Business clock changed. Review a new preview.'}
        with self.outlook.db() as db:
            self.table(db)
            old=db.execute('SELECT payload FROM scheduled_emails WHERE id=?',(action.id,)).fetchone()
            if old:
                job=self.outlook.unpack(old[0])
                return None, {'status':job['status'],'id':job['id'],'diagnostic':job.get('diagnostic')}
            if not self.outlook.get(db,'account'):
                return None, {'status':'not_sent','reason':'Connect Outlook in Settings before sending.'}
            job={'id':action.id,'kind':'chase_email','day':now.date().isoformat(),
                 'recipient':recipient,'department':action.payload.get('department'),
                 'order_ids':action.payload.get('order_ids',[action.order_id]),
                 'subject':action.payload.get('subject') or 'ThreadPilot chase-up | '+action.order_id,
                 'body':action.payload['text'],'status':'sending','scheduled_at':now.isoformat(),
                 'created_at':datetime.now(LOCAL).isoformat(),'updated_at':now.isoformat(),'clock_run_id':run_id}
            self.put(db,job)
            return job,None

    async def send_now(self, action, now):
        job,previous=await asyncio.to_thread(self.claim_now,action,now)
        return previous if job is None else await self.submit(job)

    def enqueue(self, action, now, real=None):
        if self.outlook.missing():
            return {'status':'not_sent','reason':'Configure and connect Outlook in Settings before scheduling email.'}
        real = real or datetime.now(LOCAL)
        due = datetime.fromisoformat(action.payload['send_at'])
        if due <= now:
            return {'status':'not_sent','reason':'The scheduled time passed. Request a fresh preview.'}
        recipient = email(action.payload['recipient'])
        clock_run_id=(BusinessClock(self.outlook.settings).read() or {}).get('run_id','')
        if action.payload.get('clock_run_id',clock_run_id)!=clock_run_id:
            return {'status':'not_sent','reason':'Business clock changed. Request a new email preview.'}
        with self.outlook.db() as db:
            self.table(db)
            row = db.execute('SELECT payload FROM scheduled_emails WHERE id=?',(action.id,)).fetchone()
            if row:
                return {'status':'scheduled','id':action.id}
            if not self.outlook.get(db,'account'):
                return {'status':'not_sent','reason':'Connect Outlook in Settings before scheduling email.'}
            job = {'id':action.id, 'kind':'chase_email' if action.payload.get('department') else 'customer_email','day':due.date().isoformat(),
                   'department':action.payload.get('department'),'order_ids':action.payload.get('order_ids',[action.order_id]),
                   'recipient':recipient,'subject':action.payload.get('subject') or 'ThreadPilot follow-up'+(' | '+action.order_id if action.order_id else ''),
                   'body':action.payload['text'],'status':'scheduled','scheduled_at':due.isoformat(),
                   'clock_run_id':clock_run_id,
                   'created_at':real.isoformat(),'updated_at':now.isoformat()}
            self.put(db,job)
        return {'status':'scheduled','id':action.id}

    def history(self):
        with self.outlook.db() as db:
            self.table(db)
            jobs=[self.outlook.unpack(r[0]) for r in db.execute('SELECT payload FROM scheduled_emails')]
            for job in jobs:
                if job['status']=='sending':
                    sent=db.execute('SELECT status FROM sends WHERE id=?',(job['id'],)).fetchone()
                    if sent: job.update(status=sent[0],diagnostic=self.outlook.get(db,'send:'+job['id']))
        return jobs

    def due(self, now):
        with self.outlook.db() as db:
            self.table(db)
            for row in db.execute('SELECT payload FROM scheduled_emails').fetchall():
                job=self.outlook.unpack(row[0])
                run_id=(BusinessClock(self.outlook.settings).read() or {}).get('run_id','')
                if job['status']=='scheduled' and job.get('clock_run_id','')!=run_id:
                    job.update(status='cancelled',diagnostic={'message':'Business clock changed; schedule cancelled.'},updated_at=now.isoformat())
                    self.put(db,job)
                    continue
                if job['status']=='scheduled' and datetime.fromisoformat(job['scheduled_at'])<=now:
                    job['status']='sending'; self.put(db,job)
                    return job

    async def run(self, now=None):
        if self.outlook.missing(): return
        job=await asyncio.to_thread(self.due,now or BusinessClock(self.outlook.settings).now())
        if not job:return
        return await self.submit(job)

    async def submit(self, job):
        try:
            result=await asyncio.to_thread(self.outlook.send,job['id'],{'to':[job['recipient']],'subject':job['subject'],'body':job['body']})
            job.update(status=result['status'],diagnostic=result.get('diagnostic'))
        except Exception:
            job.update(status='unknown',diagnostic={'message':'Check Outlook connection and Sent Items before retrying.'})
        job['updated_at']=BusinessClock(self.outlook.settings).now().isoformat()
        with self.outlook.db() as db:self.put(db,job)
        return {'id':job['id'],'status':job['status'],'diagnostic':job.get('diagnostic')}


async def scheduled_email_loop(app):
    service=ScheduledEmail(app.state.settings)
    while True:
        try: await service.run()
        except Exception: logging.getLogger(__name__).warning('Scheduled email check failed.')
        await asyncio.sleep(2)
