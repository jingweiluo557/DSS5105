"""The cost guard on model endpoints, and a rejected API key named as such (not as "provider unavailable")."""
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from app.main import create_app
from app.rate_limit import SlidingWindow, client_key
from fastapi.testclient import TestClient
from openai import AuthenticationError

from .test_workflow import FixedClassifier


def test_the_window_allows_the_limit_then_refuses_until_it_slides():
    now = [0.0]
    w = SlidingWindow(3, 60, clock=lambda: now[0])
    assert [w.allow('a')[0] for _ in range(3)] == [True, True, True]
    allowed, wait = w.allow('a')
    assert not allowed and 1 <= wait <= 61
    assert w.allow('b')[0], 'another device has its own window'
    now[0] = 60.1
    assert w.allow('a')[0], 'after a minute the oldest request no longer counts'
    assert SlidingWindow(0).allow('a') == (True, 0), '0 turns the guard off'


def test_the_client_is_the_first_forwarded_address():
    assert client_key({'x-forwarded-for': '203.0.113.7, 10.0.0.1'}, '10.0.0.1') == '203.0.113.7'
    assert client_key({}, '127.0.0.1') == '127.0.0.1'


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('WORKFLOW_DB', str(tmp_path / 'api.sqlite3'))
    monkeypatch.setenv('BUSINESS_NOW', '2026-04-01T09:00:00+08:00')
    monkeypatch.setenv('CHAT_REQUESTS_PER_MINUTE', '3')
    with TestClient(create_app()) as c:
        c.app.state.intent_classifier = FixedClassifier('order.lookup', order_ids=['ORD-005'])
        yield c


def test_model_endpoints_answer_429_with_retry_after_once_a_device_hits_the_limit(client: TestClient):
    assert [client.post('/chat', json={'message': 'Open ORD-005.'}).status_code for _ in range(3)] == [200, 200, 200]
    r = client.post('/api/v1/workflow/chat', json={'message': 'Open ORD-005.'})
    assert r.status_code == 429 and r.json()['error']['code'] == 'TOO_MANY_REQUESTS' and int(r.headers['retry-after']) >= 1
    assert client.get('/api/v1/health').status_code == 200, 'reading pages is never limited'
    other = client.post('/chat', json={'message': 'Open ORD-005.'}, headers={'X-Forwarded-For': '198.51.100.9'})
    assert other.status_code == 200, 'another device is not affected'


def test_a_rejected_api_key_is_reported_as_a_rejected_key(client: TestClient):
    class Rejecting:
        async def classify(self, *a):
            raise AuthenticationError('Incorrect API key provided', response=httpx.Response(401, request=httpx.Request('POST', 'https://api.openai.com')), body=None)
    client.app.state.intent_classifier = Rejecting()
    r = client.post('/chat', json={'message': 'Hello'})
    assert r.status_code == 503 and r.json()['error']['code'] == 'MODEL_KEY_REJECTED'
    assert 'OPENAI_API_KEY' in r.json()['error']['message']
