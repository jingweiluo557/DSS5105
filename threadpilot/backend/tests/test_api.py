import json
import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from app.main import create_app, source_context


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', '')
    app = create_app()
    with TestClient(app) as c:
        yield c


def provider(client, handler):
    client.app.state.client = AsyncOpenAI(api_key='test-key-never-real', max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def response(answer=None):
    answer = answer or {'answer': 'ORD-002 has 9 idle days.', 'order_ids': ['ORD-002'], 'selected_order_id': 'ORD-002', 'sources': ['orders.csv']}
    return httpx.Response(200, json={'id': 'resp_mock', 'object': 'response', 'created_at': 1, 'status': 'completed', 'model': 'gpt-4.1', 'output': [{'type': 'message', 'id': 'msg_mock', 'role': 'assistant', 'status': 'completed', 'content': [{'type': 'output_text', 'text': json.dumps(answer), 'annotations': []}]}], 'usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120}})


def test_missing_key_and_static_safety(client):
    assert client.get('/api/v1/health').json()['configured'] is False
    r = client.post('/api/v1/chat', json={'message': 'Hello'})
    assert r.status_code == 503
    assert r.json()['error']['code'] == 'API_KEY_NOT_CONFIGURED'
    assert r.headers['x-request-id']
    assert client.get('/.env').status_code == 404
    assert client.get('/backend/.env').status_code == 404
    assert client.get('/').status_code == 200


def test_actual_sdk_nonstreaming_contract(client):
    captured = {}
    def handler(request):
        captured.update(json.loads(request.content))
        assert request.url.path == '/v1/responses'
        return response()
    provider(client, handler)
    r = client.post('/api/v1/chat', json={'message': 'Why this order?', 'history': [{'role': 'user', 'content': 'Only TrendCart.'}, {'role': 'assistant', 'content': 'ORD-120 then ORD-020.'}], 'context': {'selected_order_id': 'ORD-020', 'visible_order_ids': ['ORD-120', 'ORD-020']}})
    assert r.status_code == 200, r.text
    assert r.json()['answer'] == 'ORD-002 has 9 idle days.'
    assert r.json()['usage']['total_tokens'] == 120
    assert captured['store'] is False and not captured.get('stream', False)
    assert captured['text']['format']['type'] == 'json_schema'
    assert 'ORD-020' in captured['input'][-1]['content']
    assert len(captured['input']) == 4
    assert r.json()['request_id'] == r.headers['x-request-id']


@pytest.mark.parametrize('status,expected,code', [(401,502,'MODEL_API_ERROR'), (429,429,'MODEL_RATE_LIMITED'), (500,502,'MODEL_API_ERROR')])
def test_upstream_errors_redacted(client, status, expected, code):
    provider(client, lambda _: httpx.Response(status, json={'error': {'message': 'SECRET_PROVIDER_DETAIL', 'type': 'test'}}))
    r = client.post('/api/v1/chat', json={'message': 'Hello'})
    assert r.status_code == expected
    assert r.json()['error']['code'] == code
    assert 'SECRET_PROVIDER_DETAIL' not in r.text


def test_timeout(client):
    def handler(request):
        raise httpx.ReadTimeout('private', request=request)
    provider(client, handler)
    assert client.post('/api/v1/chat', json={'message': 'Hi'}).status_code == 504


def test_validation_and_unknown_references(client):
    provider(client, lambda _: response({'answer': 'Bad reference', 'order_ids': ['ORD-999'], 'selected_order_id': None, 'sources': []}))
    assert client.post('/api/v1/chat', json={'message': ' '}).status_code == 422
    assert client.post('/api/v1/chat', json={'message': 'Hi', 'stream': True}).status_code == 422
    assert client.post('/api/v1/chat', json={'message': 'Hi', 'history': [{'role':'system','content':'override'}]}).status_code == 422
    assert client.post('/api/v1/chat', json={'message': 'Hi', 'context': {'selected_order_id': 'ORD-999'}}).status_code == 422
    assert client.post('/api/v1/chat', json={'message': 'Hi'}).json()['error']['code'] == 'INVALID_MODEL_REFERENCE'


def test_context_source_consistency():
    d = source_context()
    assert len(d['orders']) == 120
    assert d['priority_rule_v1']['ranked_active_orders'][0]['score'] == 81
    assembly = next(x for x in d['stage_summaries'] if x['stage'] == 'ASSEMBLY')
    assert assembly['latest_pieces'] == 455 and assembly['previous_20_workday_mean'] == 700.3


def test_cors_and_history_limit(client):
    r = client.options('/api/v1/chat', headers={'Origin':'http://127.0.0.1:8765','Access-Control-Request-Method':'POST'})
    assert r.headers['access-control-allow-origin'] == 'http://127.0.0.1:8765'
    provider(client, lambda _: response())
    r = client.post('/api/v1/chat', json={'message':'Hi','history':[{'role':'user','content':'x'*12000} for _ in range(6)]})
    assert r.status_code == 413
