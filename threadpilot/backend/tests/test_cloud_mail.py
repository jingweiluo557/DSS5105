"""Cloud persistence, optimistic clock updates and cross-worker claims; no real mail."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from app.config import Settings
from app.business_clock import BusinessClock, LOCAL
from app.services.outlook_service import OutlookService
from app.services.briefing_delivery import BriefingDelivery
from app.services.email_settings import EmailPreferences
from app.api.email_scheduler_api import router

@pytest.fixture
def settings():
    return Settings(_env_file=None, workflow_storage='database', outlook_client_id='fake',
        outlook_client_secret='fake', outlook_encryption_key=Fernet.generate_key().decode())

def test_shared_clock_advances_and_rejects_stale_version(settings):
    now = datetime(2026, 10, 24, 12, tzinfo=LOCAL)
    target = datetime(2026, 4, 1, 6, 59, tzinfo=LOCAL)
    BusinessClock(settings).save('demo', target, 0, now)
    assert BusinessClock(settings).now(now + timedelta(minutes=1)) == target + timedelta(minutes=1)
    with pytest.raises(HTTPException) as error:
        BusinessClock(settings).save('demo', target, 0, now)
    assert error.value.status_code == 409

def test_cloud_send_survives_restart_without_duplicate(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(OutlookService, 'access_token', lambda self: 'fake')
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: calls.append(k) or httpx.Response(202))
    mid = str(uuid4())
    payload = {'to':['test@example.com'], 'subject':'Cloud test', 'body':'Private message'}
    assert OutlookService(settings).send(mid, payload)['status'] == 'accepted'
    assert OutlookService(settings).send(mid, payload)['status'] == 'accepted'
    assert len(calls) == 1
    assert OutlookService(settings).history()[0]['body'] == payload['body']
    with OutlookService(settings).db() as db:
        assert payload['body'] not in db.execute('SELECT * FROM sends WHERE id=?', (mid,)).fetchone()['payload']

def test_cloud_transaction_rollback_and_oauth_commit(settings):
    svc = OutlookService(settings)
    with pytest.raises(RuntimeError):
        with svc.db() as db:
            svc.put(db, 'account', {'username':'test@example.com'})
            raise RuntimeError('rollback')
    assert not svc.status()['connected']
    with svc.db() as db:
        svc.put(db, 'flow', {'state':'one-use'})
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        db.execute("DELETE FROM vault WHERE name='flow'")
    with svc.db() as db: assert svc.get(db, 'flow') is None

def test_concurrent_briefing_workers_claim_once(settings):
    now = datetime(2026, 4, 1, 6, 59, tzinfo=LOCAL)
    BusinessClock(settings).save('demo', now, 0)
    svc = BriefingDelivery(settings)
    with svc.outlook.db() as db: svc.outlook.put(db, 'account', {'username':'sender@example.com'})
    svc.preferences.save(EmailPreferences(version=0, manager_email='manager@example.com', briefing_enabled=True), now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: BriefingDelivery(settings).claim(now + timedelta(minutes=1)), range(2)))
    assert sum(job is not None for job in claims) == 1
    assert len(BriefingDelivery(settings).history()) == 1

def test_timer_requires_separate_scheduler_token(settings):
    app = FastAPI(); app.state.settings = settings; app.include_router(router)
    client = TestClient(app)
    assert client.post('/api/internal/email/run').status_code == 401

@pytest.mark.parametrize('scenario', ['test_demo_659_triggers_seven_once_per_run',
    'test_ai_two_minutes_requires_confirmation_and_delivers_once'])
def test_business_time_delivery_with_shared_database(scenario, tmp_path, monkeypatch):
    from . import test_business_clock
    monkeypatch.setenv('WORKFLOW_STORAGE', 'database')
    getattr(test_business_clock, scenario)(tmp_path, monkeypatch)

def test_cloud_oauth_cookie_and_return_origin(settings, monkeypatch):
    from app.api.outlook_api import router as outlook_router
    settings.outlook_redirect_uri = 'https://api.example.com/api/outlook/callback'
    settings.public_frontend_origin = 'https://workspace.example.com'
    from pydantic import SecretStr
    settings.data_api_token = SecretStr('test-admin')
    monkeypatch.setattr(OutlookService, 'begin', lambda self: ('https://login.microsoftonline.com/', 'binding'))
    monkeypatch.setattr(OutlookService, 'finish', lambda *args: None)
    app = FastAPI(); app.state.settings = settings; app.include_router(outlook_router)
    client = TestClient(app, base_url='https://api.example.com')
    response = client.post('/api/outlook/connect?source=settings', headers={'Authorization':'Bearer test-admin'})
    assert 'SameSite=none' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie']
    response = client.get('/api/outlook/callback', follow_redirects=False)
    assert response.headers['location'] == 'https://workspace.example.com/?authorization=connected#/settings'
