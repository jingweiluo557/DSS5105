import asyncio
import json
from types import SimpleNamespace
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.services.morning_service import MorningService, MorningConflict
from app.models import Order
from sqlalchemy import update

NOW=datetime.fromisoformat('2026-10-14T08:00:00+08:00')


@pytest.fixture(autouse=True)
def dashboard_tables(business_database):
    from app.dashboard_store import metadata
    metadata.create_all(business_database.engine)


def model(bad=False, callback=None):
    async def create(**kwargs):
        if 'Audit a factory briefing' in kwargs['messages'][0]['content']:
            return SimpleNamespace(id='check-fixture',choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps({'supported':True,'issues':[]})))])
        if callback: callback()
        sections={key:{'text':'Check overdue orders and confirm production progress.',
                       'evidence':['missing' if bad else 'counts']} for key in ('yesterday','top_issue','decide')}
        return SimpleNamespace(id='real-response-fixture',choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps(sections)))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def run(service, client, now=NOW, scheduled=False):
    settings=Settings(intent_api_style='chat_completions')
    return asyncio.run(service.generate('2026-04-01',client,settings,now,scheduled))


def test_real_generation_required_and_saved_report_reused(business_database):
    s=MorningService(business_database)
    with pytest.raises(ValueError,match='not configured'):run(s,None)
    assert s.list()==[]
    result=run(s,model())
    report=result['report']
    assert report['generated_by']=='llm' and report['source']=='database_snapshot'
    assert report['facts']['counts']['in_progress']==34
    assert report['facts']['counts']['overdue']==8
    assert report['business_date']=='2026-04-01' and report['day']=='2026-10-14'
    assert report['response_id']=='real-response-fixture'
    assert run(s,None)['status']=='already_saved'
    assert run(s,None,scheduled=True)['status']=='already_saved'
    assert run(s,None,NOW.replace(hour=6),True)['status']=='not_due'


def test_ai_tasks_persist_and_model_change_regenerates_without_reopening(business_database):
    from app.services.dashboard_service import DashboardService
    service=MorningService(business_database)
    settings=Settings(intent_api_style='chat_completions',openai_model='gpt-6.1')
    base=model()
    async def create(**kwargs):
        response=await base.chat.completions.create(**kwargs)
        if 'Audit a factory briefing' not in kwargs['messages'][0]['content']:
            body=json.loads(response.choices[0].message.content)
            body['decide']={'text':'- Check ORD-002 progress.\n- Review production priorities.',
                            'evidence':['ORD-002','counts']}
            response.choices[0].message.content=json.dumps(body)
        return response
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    first=asyncio.run(service.generate('2026-04-01',client,settings,NOW))
    dash=DashboardService(business_database)
    tasks=dash.list_tasks()
    assert len(tasks)==2 and all(t['origin']=='ai' for t in tasks)
    item=next(t for t in tasks if t['order_id']=='ORD-002')
    assert dash.complete_task(item['id'],True,item['version'],NOW)
    assert asyncio.run(service.generate('2026-04-01',None,settings,NOW))['status']=='already_saved'
    settings.openai_model='other-configured-model'
    second=asyncio.run(service.generate('2026-04-01',client,settings,NOW))
    assert second['report']['id']!=first['report']['id']
    tasks=DashboardService(business_database).list_tasks()
    assert len(tasks)==2 and next(t for t in tasks if t['id']==item['id'])['done']


def test_invalid_evidence_and_concurrent_changes_do_not_archive(business_database):
    s=MorningService(business_database)
    with pytest.raises(ValueError,match='unavailable evidence'):run(s,model(True))
    assert s.list()==[]
    def change():
        with business_database.sessions.begin() as session:
            session.execute(update(Order).where(Order.order_id=='ORD-114').values(pieces=777))
    with pytest.raises(MorningConflict):run(s,model(callback=change))
    assert s.list()==[]



def test_grounding_rejection_never_saves_model_fiction(business_database):
    calls=[]
    good=model()
    async def create(**kwargs):
        calls.append(kwargs)
        if 'Audit a factory briefing' in kwargs['messages'][0]['content']:
            return SimpleNamespace(id='check',choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(
                content=json.dumps({'supported':False,'issues':['Unsupported causal claim']})))])
        return await good.chat.completions.create(**kwargs)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    s=MorningService(business_database)
    with pytest.raises(ValueError,match='fact checks'):run(s,client)
    assert len(calls)==4 and s.list()==[]


def test_api_no_mock_fallback_and_legacy_demo_routes(business_database,monkeypatch,tmp_path):
    for k,v in {'OPENAI_API_KEY':'','API_ACCESS_TOKEN':'workspace','BACKGROUND_TASKS_ENABLED':'false',
                'BUSINESS_NOW':'2026-04-01T09:00:00+08:00','WORKFLOW_DB':str(tmp_path/'wf.db')}.items():monkeypatch.setenv(k,v)
    with TestClient(create_app()) as client:
        assert client.get('/api/morning').status_code==401
        headers={'X-ThreadPilot-Token':'workspace'}
        assert client.get('/api/morning',headers=headers).json()['reports']==[]
        assert client.post('/api/morning/generate',headers=headers).status_code==422
        assert client.get('/demo/briefing_demo.html',follow_redirects=False).headers['location']=='/briefing.html'
        assert client.get('/briefing.html').status_code==200
        fake=model()
        async def close():pass
        fake.close=close;client.app.state.client=fake;client.app.state.settings.intent_api_style='chat_completions'
        report=client.post('/api/morning/generate',headers=headers).json()['report']
        assert client.get('/api/morning/reports/'+report['id'],headers=headers).json()==report
