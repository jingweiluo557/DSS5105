from datetime import datetime, timedelta
import asyncio
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Order
from app.dashboard_store import metadata
from app.services.order_records import OrderRecords
from app.services.morning_service import MorningService
from app.config import Settings
from .test_morning_ai import model

DAY = datetime.fromisoformat('2026-04-02T11:00:00+08:00')


def test_manager_chat_records_and_briefing(business_database, monkeypatch, tmp_path):
    # Use the real chat, confirmation gate, ORM write path and archived report.
    monkeypatch.setenv('WORKFLOW_DB', str(tmp_path / 'workflow.db'))
    monkeypatch.setenv('BACKGROUND_TASKS_ENABLED', 'false')
    monkeypatch.setenv('MORNING_SCHEDULER_ENABLED', 'false')
    monkeypatch.setenv('BUSINESS_NOW', DAY.isoformat())
    monkeypatch.setenv('API_ACCESS_TOKEN', 'reader')
    monkeypatch.setenv('MANAGER_ACCESS_TOKEN', 'manager')
    metadata.create_all(business_database.engine)
    records = OrderRecords(business_database)
    records.evaluate(DAY - timedelta(days=1))
    with TestClient(create_app()) as client:
        client.headers['X-ThreadPilot-Token'] = 'manager'
        def turn(message, **kw):
            r = client.post('/chat', json={'message':message, **kw})
            assert r.status_code == 200, r.text
            return r.json()
        def save(message):
            preview = turn(message)
            assert preview['confirmation_required'], preview['answer']
            args = dict(session_id=preview['state']['session_id'], confirmation_id=preview['confirmation_id'])
            assert not any(r['id'] == preview['confirmation_id'] for r in records.list())
            client.headers['X-ThreadPilot-Token'] = 'reader'
            assert 'manager' in turn('确认', **args)['answer'].lower()
            client.headers['X-ThreadPilot-Token'] = 'manager'
            assert not turn('确认', **args)['confirmation_required']
            assert 'duplicate' in turn('确认', **args)['answer'].lower()
            return preview['confirmation_id']
        for oid in ('ORD-005', 'ORD-017'):
            save(f'如果今天{oid}状态没更新，明天的晨报告诉我。')
        save('给 ORD-005 备注下，客户需求量有变化。')
        url = '/api/v1/management-records'
        assert len(client.get(url).json()['records']) == 3
        order_rows = client.get(url, params={'order_id':'ORD-005'}).json()['records']
        assert len(order_rows) == 2
        assert next(r['text'] for r in order_rows if r['kind']=='note') == '客户需求量有变化。'
        with business_database.sessions.begin() as session:
            order = session.scalar(sa.select(Order).where(Order.order_id=='ORD-017'))
            order.current_stage = 'PACKING' if order.current_stage != 'PACKING' else 'WASHING'
        tomorrow = DAY + timedelta(days=1)
        records.evaluate(tomorrow)
        records.evaluate(tomorrow)
        assert records.briefing_due(tomorrow)
        service = MorningService(business_database)
        report = asyncio.run(service.generate(str(tomorrow.date()), model(), Settings(intent_api_style='chat_completions'), tomorrow))['report']
        assert [r['order_id'] for r in report['manager_followups']] == ['ORD-005']
        assert next(r for r in records.list('ORD-005') if r['kind']=='briefing_watch')['report_id'] == report['id']
        assert records.list('ORD-017')[0]['status'] == 'changed'
        assert not records.briefing_due(tomorrow)


def test_incomplete_day_is_not_reported_as_no_change(business_database):
    from app.schemas import PendingAction
    from app.services.order_records import attach_to_report
    records = OrderRecords(business_database)
    day = DAY.date().isoformat()
    tomorrow = DAY + timedelta(days=1)
    action = PendingAction(kind='reminder', order_id='ORD-005', created_at=DAY, preview='watch',
        payload=dict(observation_day=day, report_day=tomorrow.date().isoformat(), channel='morning_briefing'))
    records.save(action, 'user-session', DAY)
    records.evaluate(DAY)
    assert records.list('ORD-005')[0]['status'] == 'pending'
    records.evaluate(tomorrow)
    assert records.list('ORD-005')[0]['status'] == 'unverified'
    with business_database.engine.connect() as db:
        transaction = db.begin()
        items = attach_to_report(db, tomorrow.date().isoformat(), 'failed-report')
        assert items[0]['result'] == 'unverified'
        transaction.rollback()
    assert records.list('ORD-005')[0]['report_id'] is None
    assert records.briefing_due(tomorrow)
