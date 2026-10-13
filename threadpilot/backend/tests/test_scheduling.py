import asyncio
import copy
import json
from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Order
from app.schemas import ChatRequest, Classification, Intent, Slots
from app.services.scheduling_service import QueueAnalysis, SchedulingService, current_snapshot
from app.services.queue_engine import project, STAGES
from app.services.dashboard_service import analyze
from app.services.snapshot_service import DatabaseDataTools
from app.scheduling_store import schedule, reviews
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore

DAY = '2026-04-06'
NOW = datetime.fromisoformat(DAY + 'T09:00:00+08:00')


def sample():
    orders = [dict(order_id='ORD-001', customer='A', pieces=2400, status='IN_PROGRESS',
                   current_stage='PACKING', due_date='2026-04-08', order_date='2026-03-01', last_activity_date=DAY),
              dict(order_id='ORD-002', customer='B', pieces=2400, status='IN_PROGRESS',
                   current_stage='PACKING', due_date='2026-04-09', order_date='2026-03-01', last_activity_date=DAY)]
    logs = [dict(date=(date(2026, 4, 4)-timedelta(weeks=n)).isoformat(), stage=s, pieces_completed=1000)
            for n in range(1, 9) for s in STAGES]
    return {'today': DAY, 'orders': orders, 'production_log': logs, 'workshops': [],
            'schedule': {'version': 0, 'priority': []}}


def test_expedite_compares_identical_scenarios_and_all_affected_orders():
    data = sample(); q = QueueAnalysis(data)
    p = q.expedite('ORD-002')
    assert q.base == {'ORD-001': 4, 'ORD-002': 6}
    assert p['days_saved'] == 2 and p['gain'] == 2 and p['cost'] == 2 and p['net'] == 0
    assert p['recommendation'] == 'later'
    assert p['affected'][0]['order_id'] == 'ORD-001'
    assert p['affected'][0]['finish_before'] == '2026-04-09'
    assert p['affected'][0]['finish_after'] == '2026-04-11'
    assert p['risk'] == q.risk(q.active[1])
    assert data == sample()  # analysis never edits the input


def test_existing_approved_priorities_remain_in_both_scenarios():
    data=sample(); data['schedule']={'version':1,'priority':['ORD-002']}
    q=QueueAnalysis(data)
    assert q.base == {'ORD-001':6,'ORD-002':4}
    assert q.expedite('ORD-002')['gain']==0
    assert not q.expedite('ORD-002')['can_apply']


def test_missing_history_and_horizon_never_turn_into_fake_gains():
    data=sample();data['production_log']=[]
    p=QueueAnalysis(data).expedite('ORD-002')
    assert p['recommendation']=='unavailable' and p['gain'] is None and not p['can_apply']
    data=sample();data['orders'][0]['pieces']=10**7
    assert QueueAnalysis(data).expedite('ORD-002')['gain'] is None


def test_stalled_order_requires_investigation():
    data=sample();data['orders'][0]['last_activity_date']='2026-03-20'
    p=QueueAnalysis(data).expedite('ORD-001')
    assert p['recommendation']=='investigate' and not p['can_apply']


@pytest.mark.parametrize('inputs,recommendation,gain,cost', [
    ([(1200,11),(6000,10),(2400,13),(1200,18),(600,13)], 'now',4,2),
    ([(6000,6),(2400,13),(2400,14),(6000,13),(1200,14)], 'trade_off',11,4),
])
def test_recommendations_include_newly_late_tradeoff(inputs,recommendation,gain,cost):
    data=sample();template=data['orders'][0]
    data['orders']=[dict(template,order_id=f'ORD-{i+1:03}',pieces=quantity,due_date=f'2026-04-{day:02}')
                    for i,(quantity,day) in enumerate(inputs)]
    p=QueueAnalysis(data).expedite('ORD-005')
    assert p['recommendation']==recommendation
    assert (p['gain'],p['cost'],p['net'])==(gain,cost,gain-cost)
    assert any(o['newly_late'] for o in p['affected'])==(recommendation=='trade_off')


def test_negative_net_does_not_recommend_expedite():
    data=sample()
    data['orders'][0].update(pieces=600,due_date='2026-04-06')
    data['orders'][1].update(pieces=600,due_date='2026-04-08')
    p=QueueAnalysis(data).expedite('ORD-002')
    assert p['gain']==0 and p['cost']==1 and p['net']==-1 and p['recommendation']=='later'


def test_preview_commit_stale_and_replay(business_database):
    db=business_database; service=SchedulingService(db)
    data=current_snapshot(db,'2026-04-01'); q=QueueAnalysis(data)
    oid=next(o['order_id'] for o in q.active if q.expedite(o['order_id'])['can_apply'])
    p=service.preview(oid,'2026-04-01')
    other=service.preview(oid,'2026-04-01')
    with db.sessions() as session:
        assert session.execute(sa.select(schedule)).first() is None
    decision=service.decide(p['review_id'],'apply','Manager','Reviewed all affected orders','2026-04-01')
    assert decision['status']=='applied'
    fresh=current_snapshot(db,'2026-04-01')
    assert fresh['schedule']['priority'][0]==oid and fresh['schedule']['version']==1
    projected=QueueAnalysis(fresh)
    assert projected.risk(next(o for o in projected.active if o['order_id']==oid))['best_date']==p['finish_after']
    assert service.decide(p['review_id'],'apply','Manager','Reviewed all affected orders','2026-04-01')['replayed']
    assert current_snapshot(db,'2026-04-01')['schedule']['version']==1
    with pytest.raises(ValueError,match='changed'):
        service.decide(other['review_id'],'apply','Manager','stale','2026-04-01')
    with pytest.raises(ValueError,match='different'):
        service.decide(p['review_id'],'reject','Manager','changed mind','2026-04-01')
    assert service.history()[0]['payload']['affected']==p['affected']


def test_business_update_invalidates_preview(business_database):
    service=SchedulingService(business_database)
    p=service.preview('ORD-005','2026-04-01')
    with business_database.sessions.begin() as session:
        order=session.scalar(sa.select(Order).where(Order.order_id=='ORD-005'))
        order.pieces+=1;order.version+=1
    with pytest.raises(ValueError,match='changed'):
        service.decide(p['review_id'],'save','Manager','old result','2026-04-01')


def test_expired_and_changed_date_require_new_review(business_database):
    service=SchedulingService(business_database)
    p=service.preview('ORD-005','2026-04-01')
    with pytest.raises(ValueError,match='changed'):
        service.decide(p['review_id'],'save','Manager','next day','2026-04-02')
    with business_database.sessions.begin() as session:
        session.execute(reviews.update().where(reviews.c.id==p['review_id']).values(created_at='2020-01-01T00:00:00+00:00'))
    with pytest.raises(ValueError,match='expired'):
        service.decide(p['review_id'],'save','Manager','expired','2026-04-01')


def test_risk_chat_and_dashboard_share_database_schedule(business_database):
    data=current_snapshot(business_database,'2026-04-01')
    expected=QueueAnalysis(data)
    dashboard=analyze(data)
    tools=DatabaseDataTools(business_database)
    for row in dashboard['orders']:
        chat=tools.assess_risk(tools.refresh_order(row['order_id']),datetime.fromisoformat('2026-04-01T09:00:00+08:00'))
        assert chat['risk_level']==row['risk']['level']==expected.risk(row)['level']


def test_chat_followup_and_actions_do_not_apply_schedule(business_database,tmp_path):
    class Classifier:
        async def classify(self,message,state,now):
            return Classification(intent=Intent.ORDER_EXPEDITE,slots=Slots(),confidence=.99)
    engine=WorkflowEngine(DatabaseDataTools(business_database),WorkflowStore(tmp_path/'workflow.db'),
                          lambda:datetime.fromisoformat('2026-04-01T09:00:00+08:00'))
    a=asyncio.run(engine.chat(ChatRequest(message='Should we expedite ORD-005?'),Classifier()))
    b=asyncio.run(engine.chat(ChatRequest(message='它会影响谁？',session_id=a.state.session_id),Classifier()))
    assert b.selected_order_id=='ORD-005'
    assert any(t.name=='assess_expedite' for t in b.tool_calls)
    assert 'Affected orders:' in b.answer
    c=asyncio.run(engine.chat(ChatRequest(message='确认',session_id=a.state.session_id),Classifier()))
    assert not current_snapshot(business_database,'2026-04-01')['schedule']['priority']


def test_manager_api_requires_both_credentials_and_confirmation(business_database,monkeypatch,tmp_path):
    for key,value in {'OPENAI_API_KEY':'','API_ACCESS_TOKEN':'workspace','BACKGROUND_TASKS_ENABLED':'false',
                      'BUSINESS_NOW':'2026-04-01T09:00:00+08:00','WORKFLOW_DB':str(tmp_path/'workflow.db')}.items():
        monkeypatch.setenv(key,value)
    with TestClient(create_app()) as client:
        assert client.get('/api/scheduling/risk').status_code==401
        headers={'X-ThreadPilot-Token':'workspace'}
        p=client.post('/api/scheduling/orders/ORD-005/preview',headers=headers).json()
        url='/api/scheduling/reviews/'+p['review_id']+'/decision'
        body={'decision':'save','reviewed_by':'Manager','note':'Review first'}
        assert client.post(url,headers=headers,json=body).status_code==401
        headers['Authorization']='Bearer test-management-token'
        assert client.post(url,headers=headers,json=body).status_code==409
        headers['X-Confirm-Write']='true'
        assert client.post(url,headers=headers,json=body).json()['status']=='saved'
        assert client.get('/api/scheduling/history',headers=headers).json()[0]['note']=='Review first'
        assert client.post(url,headers=headers,json={**body,'note':' '}).status_code==422


def test_migration_from_0005_preserves_data_and_empty_install(tmp_path, monkeypatch):
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    url='sqlite:///'+(tmp_path/'migration.db').as_posix()
    monkeypatch.setenv('DATABASE_URL',url)
    command.upgrade(config,'0005')
    engine=sa.create_engine(url)
    with engine.begin() as db:
        db.execute(sa.text('INSERT INTO sync_lock(id) VALUES (42)'))
    command.upgrade(config,'head')
    with engine.connect() as db:
        assert db.execute(sa.text('SELECT id FROM sync_lock WHERE id=42')).scalar()==42
        assert 'dispatch_reviews' in sa.inspect(db).get_table_names()
    engine.dispose()
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+(tmp_path/'fresh.db').as_posix())
    command.upgrade(config,'head')


def test_concurrent_managers_cannot_apply_two_stale_plans(business_database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    service=SchedulingService(business_database)
    q=QueueAnalysis(current_snapshot(business_database,'2026-04-01'))
    oid=next(o['order_id'] for o in q.active if q.expedite(o['order_id'])['can_apply'])
    plans=[service.preview(oid,'2026-04-01') for _ in range(2)]
    barrier=Barrier(2)
    def apply(p):
        barrier.wait()
        try:
            return service.decide(p['review_id'],'apply','Manager','Review','2026-04-01')['status']
        except ValueError:
            return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(apply,plans))==['applied','stale']
    assert current_snapshot(business_database,'2026-04-01')['schedule']['version']==1
