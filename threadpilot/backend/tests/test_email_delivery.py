import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.config import Settings
from app.services.email_settings import EmailPreferences
from app.services.briefing_delivery import BriefingDelivery
from app.services.dashboard_service import LOCAL
from app.api.email_api import router


@pytest.fixture
def delivery(tmp_path):
    settings = Settings(_env_file=None, outlook_client_id='fake', outlook_client_secret='fake',
        outlook_encryption_key=Fernet.generate_key().decode(), outlook_store=tmp_path/'mail.sqlite3',
        data_api_token='owner')
    service = BriefingDelivery(settings)
    with service.outlook.db() as db:
        service.outlook.put(db, 'account', {'username':'sender@outlook.com'})
    service.preferences.save(EmailPreferences(version=0, manager_email='manager@example.com', briefing_enabled=True),
                             datetime(2026,10,23,6,0,tzinfo=LOCAL))
    return service


def report(day='2026-10-23'):
    return {'report': {'id':'report-1','day':day,'business_date':'2026-04-01',
        'yesterday':'Production facts','top_issue':'Priority facts','decide':'Decisions'}}


def test_schedule_timezone_restart_and_no_duplicate(delivery, monkeypatch):
    calls=[]
    monkeypatch.setattr(type(delivery.outlook),'send',lambda self,id,payload: calls.append(payload) or {'status':'accepted'})
    async def generate(): return report()
    async def run():
        before=datetime(2026,10,23,6,59,tzinfo=LOCAL)
        assert (await delivery.run(None,before,generate))['status']=='not_due_or_claimed'
        assert (await delivery.run(None,before+timedelta(minutes=1),generate))['status']=='accepted'
        restarted=BriefingDelivery(delivery.outlook.settings)
        assert (await restarted.run(None,before+timedelta(hours=1),generate))['status']=='not_due_or_claimed'
    asyncio.run(run())
    assert len(calls)==1 and calls[0]['to']==['manager@example.com']
    row=delivery.history()[0]
    assert row['status']=='accepted' and row['report_id']=='report-1'
    assert 'Production facts' in row['body']
    assert b'Production facts' not in delivery.outlook.settings.outlook_store.read_bytes()


def test_late_activation_and_version_conflict(delivery):
    p=delivery.preferences.read()
    p['briefing_enabled']=False
    delivery.preferences.save(EmailPreferences(**p))
    p=delivery.preferences.read();p['briefing_enabled']=True
    saved=delivery.preferences.save(EmailPreferences(**p),datetime(2026,10,23,18,tzinfo=LOCAL))
    assert saved['start_day']=='2026-10-24'
    assert delivery.claim(datetime(2026,10,23,19,tzinfo=LOCAL)) is None
    with pytest.raises(HTTPException):delivery.preferences.save(EmailPreferences(**p))


@pytest.mark.parametrize('change', ['disable', 'recipient'])
def test_settings_change_during_generation_cancels(delivery, monkeypatch, change):
    def forbidden(*args):raise AssertionError('Must not send')
    monkeypatch.setattr(delivery.outlook,'send',forbidden)
    async def generate():
        p=delivery.preferences.read()
        p.update({'briefing_enabled':False} if change=='disable' else {'manager_email':'new@example.com'})
        delivery.preferences.save(EmailPreferences(**p))
        return report()
    asyncio.run(delivery.run(None,datetime(2026,10,23,7,tzinfo=LOCAL),generate))
    assert delivery.history()[0]['status']=='cancelled'


def test_generation_retry_bounded_and_no_stale_report(delivery,monkeypatch):
    calls=[]
    monkeypatch.setattr(delivery.outlook,'send',lambda *args:calls.append(args))
    async def generate():return report('2026-10-22')
    async def run():
        for minute in (0,5,10,15):
            await delivery.run(None,datetime(2026,10,23,7,minute,tzinfo=LOCAL),generate)
    asyncio.run(run())
    assert not calls
    assert delivery.history()[0]['attempts']==3
    assert delivery.history()[0]['status']=='generation_failed'


def test_concurrent_claims(delivery):
    async def run():
        return await asyncio.gather(*[asyncio.to_thread(delivery.claim,datetime(2026,10,23,7,tzinfo=LOCAL)) for _ in range(6)])
    assert sum(row is not None for row in asyncio.run(run()))==1


def test_manual_historical_delivery_preserves_schedule(delivery, monkeypatch):
    before=delivery.preferences.read()
    calls=[]
    monkeypatch.setattr(delivery.outlook,'send',lambda *args:calls.append(args) or {'status':'accepted'})
    async def generate(): return report('2026-04-01')
    async def run():
        for _ in range(2):
            await delivery.run(None,generate=generate,manual_day=date(2026,4,1))
    asyncio.run(run())
    assert len(calls)==1
    assert delivery.preferences.read()==before
    assert delivery.history()[0]['trigger']=='manual'


def test_api_permissions_contacts_and_activity(delivery):
    app=FastAPI();app.state.settings=delivery.outlook.settings;app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/api/email/settings').status_code==200
        headers={'X-Confirm-Write':'true'}
        p=client.get('/api/email/settings',headers=headers).json()['preferences']
        p['customers']=[{'customer':'Acme','name':'Jane','email':'jane@example.com'}]
        assert client.put('/api/email/settings',json=p,headers={'Authorization':'Bearer owner'}).status_code==409
        saved=client.put('/api/email/settings',json=p,headers=headers)
        assert saved.status_code==200 and saved.json()['preferences']['customers'][0]['customer']=='Acme'
        p=saved.json()['preferences'];p['manager_email']='invalid'
        assert client.put('/api/email/settings',json=p,headers=headers).status_code==422
        assert client.get('/api/email/activity',headers=headers).json()=={'entries':[]}


def test_workspace_access_protects_email_without_admin_key(delivery):
    from app.main import create_app
    app=create_app()
    app.state.settings=delivery.outlook.settings.model_copy(update={'api_access_token': SecretStr('workspace')})
    # No lifespan: keep the test on the isolated email store, without any workers.
    client=TestClient(app)
    for path in ('settings','activity'):
        assert client.get('/api/email/'+path).status_code==401
        assert client.get('/api/email/'+path,headers={'X-ThreadPilot-Token':'workspace'}).status_code==200
    assert client.post('/api/email/disconnect',headers={'X-Confirm-Write':'true'}).status_code==401
    assert client.post('/api/email/disconnect',headers={'X-ThreadPilot-Token':'workspace'}).status_code==409
    assert client.post('/api/email/disconnect',headers={'X-ThreadPilot-Token':'workspace','X-Confirm-Write':'true'}).status_code==200


@pytest.mark.parametrize('outcome',['rejected','unknown'])
def test_failed_submission_recorded_without_retry(delivery,monkeypatch,outcome):
    calls=[]
    monkeypatch.setattr(delivery.outlook,'send',lambda *args:calls.append(args) or {'status':outcome,'diagnostic':{'message':'Check mailbox'}})
    async def generate():return report()
    async def run():
        for hour in (7,8):await delivery.run(None,datetime(2026,10,23,hour,tzinfo=LOCAL),generate)
    asyncio.run(run())
    assert len(calls)==1 and delivery.history()[0]['status']==outcome
