from datetime import datetime
from uuid import uuid4
import copy

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.dashboard_store import metadata, tasks, briefings
from app.services.dashboard_service import DashboardService, analyze, forecast_matches
from app.services.snapshot_service import snapshot
from app.main import create_app
from app.forecast_store import metadata as prediction_metadata, import_forecasts, predictions, batches
from app.services.dashboard_service import forecast_asset

def now(value='2026-10-10T07:00:00+08:00'):
    return datetime.fromisoformat(value)

def setup(database):
    from app.briefing_email import metadata as email_metadata
    email_metadata.create_all(database.engine)
    metadata.create_all(database.engine)
    prediction_metadata.create_all(database.engine)
    import_forecasts(database,forecast_asset())
    return DashboardService(database), snapshot(database, '2026-04-01')

def test_prediction_matching_and_exclusive_health(business_database):
    _,data=setup(business_database)
    assert forecast_matches(data)
    result=analyze(data)
    assert result['counts']=={'in_progress':34,'overdue':8,'due_today':1,'idle':2,'priority':2}
    health=result['health']
    assert sum(health[k] for k in ['late','at_risk','on_track'])==34
    assert health['late']==8
    assert not result['sales_forecast_available']
    changed=copy.deepcopy(data);changed['today']='2026-04-02'
    assert not forecast_matches(changed)
    changed=copy.deepcopy(data);changed['workshops'][0]['current_queue_days']='100'
    assert not forecast_matches(changed)
    changed=copy.deepcopy(data);changed['production_log'][0]['pieces_completed']='1'
    assert not forecast_matches(changed)

def test_shared_tasks_retries_reopen_and_no_order_mutation(business_database):
    service,data=setup(business_database)
    first=service.get(data);second=DashboardService(business_database).get(data)
    assert len(first['tasks'])==len(second['tasks'])
    item=first['tasks'][0]
    assert service.complete_task(item['id'],True,item['version'],now())
    assert not service.complete_task(item['id'],False,item['version'],now())
    assert next(r for r in service.get(data)['tasks'] if r['id']==item['id'])['done']
    assert snapshot(business_database,'2026-04-01')['orders']==data['orders']
    task_id=uuid4()
    a=service.create_task('Call the planner',data['today'],now(),task_id)
    assert a==service.create_task('Call the planner',data['today'],now(),task_id)
    assert sum(r['origin']=='manual' for r in service.list_tasks())==1
    data['today']='2026-04-02'
    assert not next(r for r in service.get(data)['tasks'] if r['id']==item['id'])['done']

def test_schedule_timezone_idempotence_archive_and_business_clock(business_database):
    service,data=setup(business_database)
    assert service.generate_due(data,now('2026-10-09T22:59:00+00:00'))['status']=='not_due'
    assert service.generate_due(data,now('2026-10-09T23:00:00+00:00'))['status']=='completed'
    assert service.generate_due(data,now('2026-10-10T10:00:00+08:00'))['status']=='already_saved'
    before=service.get(data)['briefings'][0]
    assert before['business_date']=='2026-04-01' and before['day']=='2026-10-10'
    assert service.generate_due(data,now('2026-10-11T07:00:00+08:00'))['status']=='completed'
    after=service.get(data)['briefings']
    assert len(after)==2 and after[1]==before

def test_dashboard_api_auth_and_shared_task_update(business_database,monkeypatch):
    setup(business_database)
    for k,v in {'OPENAI_API_KEY':'','API_ACCESS_TOKEN':'test-access','SCHEDULER_TOKEN':'timer-secret',
                'BUSINESS_NOW':'2026-04-01T12:00:00+08:00','BACKGROUND_TASKS_ENABLED':'false',
                'MORNING_SCHEDULER_ENABLED':'false','SERVE_FRONTEND':'false'}.items():monkeypatch.setenv(k,v)
    with TestClient(create_app()) as client:
        assert client.get('/api/dashboard').status_code==401
        headers={'X-ThreadPilot-Token':'test-access'}
        assert client.get('/api/dashboard',headers=headers).status_code==200
        assert client.post('/api/internal/briefings/run',headers=headers).status_code==401
        assert client.post('/api/internal/briefings/run',headers={'Authorization':'Bearer timer-secret'}).status_code==200
        task_id=str(uuid4())
        assert client.post('/api/dashboard/tasks',headers=headers,json={'id':task_id,'title':'  '}).status_code==422
        added=client.post('/api/dashboard/tasks',headers=headers,json={'id':task_id,'title':'Test task'})
        assert added.status_code==201
        url='/api/dashboard/tasks/'+added.json()['id']
        assert client.put(url,headers=headers,json={'done':True,'version':1}).status_code==200
        assert client.put(url,headers=headers,json={'done':False,'version':1}).status_code==409
        predictions_response=client.get('/api/predictions',headers=headers).json()
        assert len(predictions_response['rows'])==34 and predictions_response['valid']
        evidence=client.get('/api/predictions/ORD-107',headers=headers).json()
        assert evidence['prediction']['delay_probability']==.993
        assert evidence['evidence']['predict_order_delay']['data']['features']['days_to_due']==-16
        assert client.get('/api/predictions/ORD-999',headers=headers).status_code==404
        assert client.get('/api/dashboard/sources/production',headers=headers).status_code==200

def test_prediction_import_idempotent_and_advice_bounded(business_database):
    service,data=setup(business_database)
    imported=import_forecasts(business_database,forecast_asset())
    assert imported['rows']==34
    with business_database.engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(predictions))==34
        assert db.scalar(select(func.count()).select_from(batches))==1
    result=service.get(data)
    assert 2<=len(result['advice'])<=3
    assert all(a['source'] in ('priority','production','capacity') for a in result['advice'])


def test_briefing_email_archive_edit_conflict_and_auth(business_database, monkeypatch):
    service, data = setup(business_database)
    service.generate_due(data, now())
    for k, v in {'OPENAI_API_KEY':'', 'API_ACCESS_TOKEN':'test-access',
                 'BACKGROUND_TASKS_ENABLED':'false', 'MORNING_SCHEDULER_ENABLED':'false',
                 'SERVE_FRONTEND':'false'}.items(): monkeypatch.setenv(k, v)
    url='/api/dashboard/briefings/2026-10-10/email'
    headers={'X-ThreadPilot-Token':'test-access'}
    with TestClient(create_app()) as client:
        assert client.post(url).status_code == 401
        assert client.post('/api/dashboard/briefings/2099-01-01/email',headers=headers).status_code == 404
        draft=client.post(url,headers=headers).json()
        assert '2026-04-01' in draft['body']
        assert service.get(data)['briefings'][0]['yesterday'] in draft['body']
        assert draft['version'] == 1
        update={'subject':'Edited summary', 'body':'Please review <urgent> & capacity.', 'version':1}
        saved=client.put(url,headers=headers,json=update)
        assert saved.status_code == 200 and saved.json()['version'] == 2
        assert client.put(url,headers=headers,json=update).status_code == 409
        assert client.post(url,headers=headers).json()['body'] == update['body']
        assert client.put(url,headers=headers,json={**update,'subject':'Hi\r\nBcc: injected'}).status_code == 422
        assert client.put(url,headers=headers,json={**update,'body':'   '}).status_code == 422
        from app.briefing_email import drafts
        with business_database.engine.connect() as db:
            assert db.scalar(select(func.count()).select_from(drafts)) == 1
            assert '2026-04-01' in db.scalar(select(drafts.c.source_payload))
