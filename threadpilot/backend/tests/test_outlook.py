import logging
import time
from uuid import uuid4
from urllib.parse import urlsplit, parse_qs
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.config import Settings
from app.api.outlook_api import router, COOKIE, RedactOAuthQuery
from app.services.outlook_service import OutlookService


@pytest.fixture
def svc(tmp_path):
    return OutlookService(Settings(_env_file=None, outlook_client_id='test-client',
        outlook_client_secret='test-secret', outlook_encryption_key=Fernet.generate_key().decode(),
        outlook_store=tmp_path/'outlook.sqlite3', data_api_token='admin-token'))


class Cache:
    def serialize(self): return 'encrypted-cache-test'


class Identity:
    calls = 0
    def initiate_auth_code_flow(self, scopes, **kwargs):
        assert scopes == ['https://graph.microsoft.com/Mail.Send']
        return {'state':'state-123', 'auth_uri':'https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?state=state-123', 'code_verifier':'private-verifier'}
    def acquire_token_by_auth_code_flow(self, flow, params):
        self.calls += 1
        return {'access_token':'secret-access', 'id_token_claims':{'tid':'9188040d-6c67-4c5b-b112-36a304b66dad','oid':'oid-1'}}
    def get_accounts(self): return [{'local_account_id':'oid-1','username':'owner@outlook.com'}]
    def acquire_token_silent_with_error(self, scopes, account):
        return {'access_token':'refreshed-token'}


def test_callback_binding_replay_encryption_refresh(svc, monkeypatch):
    identity=Identity()
    monkeypatch.setattr(svc,'client',lambda db:(identity,Cache()))
    _,binding=svc.begin()
    params={'state':'state-123','code':'one-time-code'}
    for bad_params,bad_binding in [(params,'wrong'),({'state':'wrong'},binding)]:
        with pytest.raises(HTTPException): svc.finish(bad_params,bad_binding)
    assert identity.calls==0
    svc.finish(params,binding)
    assert svc.status()['account']=='owner@outlook.com'
    assert svc.access_token()=='refreshed-token'
    with pytest.raises(HTTPException): svc.finish(params,binding)
    raw=svc.settings.outlook_store.read_bytes()
    assert b'encrypted-cache-test' not in raw and b'private-verifier' not in raw
    svc.disconnect()
    assert not svc.status()['connected']


def test_expired_flow(svc,monkeypatch):
    monkeypatch.setattr(svc,'client',lambda db:(Identity(),Cache()))
    _,binding=svc.begin()
    with svc.db() as db:
        p=svc.get(db,'flow');p['expires']=time.time()-1;svc.put(db,'flow',p)
    with pytest.raises(HTTPException): svc.finish({'state':'state-123'},binding)


@pytest.mark.parametrize('result,status',[(202,'accepted'),(400,'rejected'),(401,'rejected'),(429,'rejected'),(503,'unknown'),('timeout','unknown')])
def test_send_outcomes_and_no_duplicate(svc,monkeypatch,result,status):
    calls=[]
    monkeypatch.setattr(svc,'access_token',lambda:'private-token')
    def post(url,**kwargs):
        calls.append(kwargs)
        if result=='timeout': raise httpx.ReadTimeout('do not leak credentials')
        return httpx.Response(result)
    monkeypatch.setattr(httpx,'post',post)
    mid=str(uuid4());payload={'to':['recipient@example.com'],'subject':'Test','body':'private-content'}
    assert svc.send(mid,payload)['status']==status
    assert svc.send(mid,payload)['status']==status
    assert len(calls)==1
    assert calls[0]['json']['saveToSentItems'] is True
    assert svc.history()[0]['body']=='private-content'
    assert b'private-content' not in svc.settings.outlook_store.read_bytes()
    with pytest.raises(HTTPException): svc.send(mid,{**payload,'subject':'changed'})


def test_http_admin_confirmation_and_public_callback(svc,monkeypatch):
    app=FastAPI();app.state.settings=svc.settings;app.include_router(router)
    client=TestClient(app)
    assert client.get('/api/outlook/status').status_code==401
    headers={'Authorization':'Bearer admin-token'}
    payload={'id':str(uuid4()),'to':['a@example.com'],'subject':'Test','body':'Hello','confirmed':True}
    assert client.post('/api/outlook/send',headers=headers,json=payload).status_code==409
    headers['X-Confirm-Write']='true'
    assert client.post('/api/outlook/send',headers=headers,json={**payload,'confirmed':False}).status_code==422
    assert client.post('/api/outlook/send',headers=headers,json={**payload,'to':['bad\r\naddress']}).status_code==422
    assert client.post('/api/outlook/send',headers=headers,json=payload).status_code==409
    result=client.get('/api/outlook/callback?state=bad&code=secret',follow_redirects=False)
    assert result.status_code==303 and result.headers['location'].endswith('authorization=failed')
    assert 'secret' not in result.text and result.headers['Cache-Control']=='no-store'


def test_missing_config_and_log_redaction(tmp_path):
    svc=OutlookService(Settings(_env_file=None,outlook_client_id='',outlook_client_secret='',outlook_encryption_key=''))
    assert not svc.status()['configured']
    record=logging.LogRecord('uvicorn.access',20,'',0,'%s %s %s %s %s',('client','GET','/api/outlook/callback?code=secret','1.1',303),None)
    RedactOAuthQuery().filter(record)
    assert 'secret' not in record.getMessage()


def test_rejection_diagnostic_persisted_redacted_and_reused(svc, monkeypatch):
    monkeypatch.setattr(svc, 'access_token', lambda: 'private-access-token')
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(403, json={'error': {'code': 'ErrorAccessDenied',
            'message': 'Denied private-access-token test-secret Bearer abc'}},
            headers={'request-id': 'trace-1'})
    monkeypatch.setattr(httpx, 'post', post)
    mid = str(uuid4())
    payload = {'to':['a@example.com'], 'subject':'test', 'body':'body'}
    result = svc.send(mid, payload)
    assert result['diagnostic']['http_status'] == 403
    assert result['diagnostic']['code'] == 'ErrorAccessDenied'
    assert 'private-access-token' not in result['diagnostic']['message']
    assert 'test-secret' not in result['diagnostic']['message']
    assert 'abc' not in result['diagnostic']['message']
    assert svc.send(mid, payload) == result
    assert len(calls) == 1
    svc.disconnect()
    assert svc.history()[0]['diagnostic'] == result['diagnostic']
