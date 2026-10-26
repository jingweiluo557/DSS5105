import asyncio
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from app.business_clock import BusinessClock, LOCAL
from app.config import Settings
from app.services.briefing_delivery import BriefingDelivery
from app.services.email_settings import EmailPreferences
from app.services.scheduled_email import ScheduledEmail
from app.schemas import PendingAction, ChatRequest, DialogState
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore
from app.workflow_tools import DataTools
from app.conversation import ConversationAgent
from .test_workflow import DATA


def setup(tmp_path):
    s=Settings(_env_file=None,business_clock_store=tmp_path/'clock.db',outlook_store=tmp_path/'outlook.db',
        outlook_client_id='test',outlook_client_secret='test',outlook_encryption_key=Fernet.generate_key().decode())
    svc=BriefingDelivery(s)
    with svc.outlook.db() as db:svc.outlook.put(db,'account',{'username':'test@outlook.com'})
    svc.preferences.save(EmailPreferences(version=0,manager_email='manager@example.com',briefing_enabled=True),
        datetime(2026,10,23,18,tzinfo=LOCAL))
    return s,svc


def test_clock_advances_and_survives_restart(tmp_path):
    s,_=setup(tmp_path);real=datetime(2026,10,23,20,tzinfo=LOCAL)
    target=datetime(2026,4,1,6,59,tzinfo=LOCAL)
    BusinessClock(s).save('demo',target,0,real)
    assert BusinessClock(s).now(real+timedelta(seconds=60))==target+timedelta(seconds=60)
    assert BusinessClock(s).now(real+timedelta(seconds=120))==target+timedelta(seconds=120)


def test_demo_659_triggers_seven_once_per_run(tmp_path,monkeypatch):
    s,svc=setup(tmp_path);clock=BusinessClock(s)
    real=datetime(2026,10,23,20,tzinfo=LOCAL);target=datetime(2026,4,1,6,59,tzinfo=LOCAL)
    sent=[]
    monkeypatch.setattr(svc.outlook,'send',lambda *args:sent.append(args) or {'status':'accepted'})
    async def generate():return {'report':{'day':'2026-04-01','id':'r','business_date':'2026-04-01','yesterday':'p','top_issue':'i','decide':'d'}}
    async def run():
        for version in (0,1):
            clock.save('demo',target,version,real)
            assert (await svc.run(None,clock.now(real+timedelta(seconds=59)),generate))['status']=='not_due_or_claimed'
            assert (await svc.run(None,clock.now(real+timedelta(seconds=60)),generate))['status']=='accepted'
            await svc.run(None,clock.now(real+timedelta(seconds=65)),generate)
    asyncio.run(run())
    assert len(sent)==2 and sent[0][0]!=sent[1][0]
    assert len(svc.history())==2
    assert svc.preferences.read()['manager_email']=='manager@example.com'


def test_ai_two_minutes_requires_confirmation_and_delivers_once(tmp_path,monkeypatch):
    s,_=setup(tmp_path);now=datetime(2026,4,1,6,59,tzinfo=LOCAL)
    engine=WorkflowEngine(DataTools(DATA),WorkflowStore(tmp_path/'workflow.db'),lambda:now)
    engine.email_scheduler=ScheduledEmail(s)
    sent=[]
    monkeypatch.setattr(engine.email_scheduler.outlook,'send',lambda *args:sent.append(args) or {'status':'accepted'})
    agent=ConversationAgent(None)
    state=DialogState();engine.store.save(state)
    async def run():
        await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005 to customer@example.com',session_id=state.session_id),agent)
        preview=await engine.chat(ChatRequest(message='Send draft 1 in 2 minutes',session_id=state.session_id),agent)
        assert preview.confirmation_required and not sent and not engine.email_scheduler.history()
        result=await engine.chat(ChatRequest(message='confirm',session_id=state.session_id,confirmation_id=preview.confirmation_id),agent)
        assert 'scheduled' in result.answer and not sent
        await engine.email_scheduler.run(now+timedelta(seconds=119));assert not sent
        await engine.email_scheduler.run(now+timedelta(seconds=120));assert len(sent)==1
        await engine.email_scheduler.run(now+timedelta(seconds=130));assert len(sent)==1
    asyncio.run(run())


def test_new_demo_cancels_old_pending_email(tmp_path,monkeypatch):
    s,_=setup(tmp_path);clock=BusinessClock(s);now=datetime(2026,4,1,6,59,tzinfo=LOCAL)
    clock.save('demo',now,0)
    service=ScheduledEmail(s)
    action=PendingAction(kind='send',order_id='',payload={'recipient':'customer@example.com','text':'hello','send_at':(now+timedelta(minutes=2)).isoformat()},preview='review',created_at=now)
    service.enqueue(action,now)
    clock.save('demo',now,1)
    assert service.due(now+timedelta(minutes=3)) is None
    assert service.history()[0]['status']=='cancelled'
