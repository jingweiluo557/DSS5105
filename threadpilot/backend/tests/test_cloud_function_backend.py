"""Cloud storage, restart continuity, auth and scheduler regressions."""
import asyncio
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, func

from app.main import create_app
from app.schemas import DialogState, PendingAction, ChatRequest
from app.sql_workflow_store import SQLWorkflowStore, replies, notifications
from app.workflow_engine import WorkflowEngine
from app.services.snapshot_service import DatabaseDataTools
from .test_workflow import FixedClassifier

NOW = datetime.fromisoformat('2026-04-01T09:00:00+08:00')


def test_conversation_survives_new_store_instance(business_database):
    tools = DatabaseDataTools(business_database)
    first = WorkflowEngine(tools, SQLWorkflowStore(business_database.engine), lambda: NOW)
    result = asyncio.run(first.chat(ChatRequest(message='Open ORD-005'), FixedClassifier('order.lookup', order_ids=['ORD-005'])))
    second = WorkflowEngine(tools, SQLWorkflowStore(business_database.engine), lambda: NOW)
    resumed = asyncio.run(second.chat(ChatRequest(message='Refresh it', session_id=result.state.session_id), FixedClassifier('order.refresh', reference='active')))
    assert resumed.state.active_order == 'ORD-005'
    assert resumed.state.revision == 2


def test_confirmation_survives_restart(business_database):
    store = SQLWorkflowStore(business_database.engine)
    state = DialogState(active_order='ORD-005', pending_action=PendingAction(kind='note', order_id='ORD-005',
        payload={'note': 'Restart-safe note'}, preview='Save note', created_at=NOW))
    store.save(state)
    restarted = SQLWorkflowStore(business_database.engine)
    restored = restarted.load(state.session_id)
    first = restarted.commit_local(restored.pending_action, state.session_id, NOW)
    repeated = store.commit_local(restored.pending_action, state.session_id, NOW)
    assert first['id'] == repeated['id']
    assert store.action_result(first['id'], 'different-session') is None
    with pytest.raises(ValueError):
        store.commit_local(restored.pending_action, 'different-session', NOW)


def test_reminder_and_reply_deduplication(business_database):
    store = SQLWorkflowStore(business_database.engine)
    tools = DatabaseDataTools(business_database)
    state = DialogState()
    store.save(state)
    action = PendingAction(kind='reminder', order_id='ORD-005', preview='Watch', created_at=NOW,
        payload={'condition': 'no_reply', 'deadline': (NOW + timedelta(hours=1)).isoformat(), 'since': NOW.isoformat()})
    store.commit_local(action, state.session_id, NOW)
    restarted = SQLWorkflowStore(business_database.engine)
    restarted.evaluate_reminders(NOW + timedelta(hours=2), tools)
    store.evaluate_reminders(NOW + timedelta(hours=2), tools)
    assert len(store.notifications(state.session_id)) == 1
    store.record_reply('event-1', 'ORD-005', NOW)
    restarted.record_reply('event-1', 'ORD-005', NOW)
    with business_database.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(replies)) == 1
        assert db.scalar(select(func.count()).select_from(notifications)) == 1


def test_sql_history_survives_restart(business_database):
    store = SQLWorkflowStore(business_database.engine)
    store.save_history('sql-1', [{'role': 'user', 'content': 'orders?'}])
    assert SQLWorkflowStore(business_database.engine).load_history('sql-1')[0]['content'] == 'orders?'
    with pytest.raises(KeyError):
        store.load_history('missing')


def test_cloud_api_auth_scheduler_and_no_background_files(business_database, tmp_path, monkeypatch):
    monkeypatch.setenv('WORKFLOW_STORAGE', 'database')
    monkeypatch.setenv('BACKGROUND_TASKS_ENABLED', 'false')
    monkeypatch.setenv('SERVE_FRONTEND', 'false')
    monkeypatch.setenv('WORKFLOW_DB', str(tmp_path / 'must-not-exist.sqlite3'))
    monkeypatch.setenv('OPENAI_API_KEY', '')
    monkeypatch.setenv('API_ACCESS_TOKEN', 'test-access')
    monkeypatch.setenv('SCHEDULER_TOKEN', 'test-scheduler')
    with TestClient(create_app()) as client:
        assert client.get('/api/v1/health').status_code == 200
        denied = client.get('/api/snapshot', headers={'Origin': 'http://localhost:8765'})
        assert denied.status_code == 401
        assert denied.headers['access-control-allow-origin'] == 'http://localhost:8765'
        assert client.get('/api/snapshot', headers={'X-ThreadPilot-Token': 'test-access'}).status_code == 200
        assert client.post('/api/internal/reminders/run').status_code == 401
        assert client.post('/api/internal/reminders/run', headers={'Authorization': 'Bearer test-access'}).status_code == 401
        assert client.post('/api/internal/reminders/run', headers={'Authorization': 'Bearer test-scheduler'}).json()['status'] == 'completed'
        assert not client.app.state.sync.scheduler.running
        assert client.get('/').status_code == 404
    assert not (tmp_path / 'must-not-exist.sqlite3').exists()
