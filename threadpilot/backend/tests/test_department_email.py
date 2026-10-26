import asyncio
from datetime import datetime
import pytest
from pydantic import ValidationError
from app.business_clock import LOCAL
from app.schemas import ChatRequest, PendingAction
from app.services.email_settings import EmailPreferences
from app.services.scheduled_email import ScheduledEmail
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore
from app.workflow_tools import DataTools
from app.conversation import ConversationAgent
from .test_business_clock import setup
from .test_workflow import DATA


def configured(tmp_path):
    s,svc=setup(tmp_path)
    prefs=svc.preferences.read()
    prefs['departments']={d:d.lower()+'@example.com' for d in ('KNITTING','ASSEMBLY','WASHING','PACKING')}
    svc.preferences.save(EmailPreferences(**prefs))
    now=datetime(2026,4,1,9,tzinfo=LOCAL)
    engine=WorkflowEngine(DataTools(DATA),WorkflowStore(tmp_path/'chat.db'),lambda:now)
    engine.email_scheduler=ScheduledEmail(s)
    return engine,svc,now


def test_department_draft_review_real_connector_and_duplicate_protection(tmp_path,monkeypatch):
    engine,svc,now=configured(tmp_path);agent=ConversationAgent(None);calls=[]
    monkeypatch.setattr(engine.email_scheduler.outlook,'send',lambda *args:calls.append(args) or {'status':'accepted','diagnostic':{'http_status':202}})
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),agent)
        draft=r.state.chase_drafts[0];stage=engine.tools.refresh_order('ORD-005').record['current_stage']
        assert draft['department']==stage and draft['recipient']==stage.lower()+'@example.com'
        assert not calls and not r.confirmation_required
        r=await engine.chat(ChatRequest(message='Preview draft 1',session_id=r.state.session_id),agent)
        assert r.confirmation_required and 'Subject:' in r.answer and draft['recipient'] in r.answer and not calls
        action=r.state.pending_action
        r=await engine.chat(ChatRequest(message='send now',session_id=r.state.session_id,confirmation_id=r.confirmation_id),agent)
        assert 'Microsoft accepted' in r.answer and not r.confirmation_required
        assert calls[0][1]['body']==draft['text'] and calls[0][1]['to']==[draft['recipient']]
        assert calls[0][1]['subject']==draft['subject']
        await engine.email_scheduler.send_now(action,now)
        assert len(calls)==1
        log=engine.email_scheduler.history()[0]
        assert log['kind']=='chase_email' and log['department']==stage and log['order_ids']==['ORD-005']
    asyncio.run(run())


def test_missing_department_email_never_sends(tmp_path):
    engine,svc,now=configured(tmp_path)
    prefs=svc.preferences.read();prefs['departments']={};svc.preferences.save(EmailPreferences(**prefs))
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        assert len(r.state.chase_drafts)==1
        r=await engine.chat(ChatRequest(message='Preview draft 1',session_id=r.state.session_id),ConversationAgent(None))
        assert not r.confirmation_required and 'department email' in r.answer
        assert not engine.email_scheduler.history()
    asyncio.run(run())


@pytest.mark.parametrize('status',['rejected','unknown'])
def test_failed_send_is_logged_and_not_retried(tmp_path,monkeypatch,status):
    engine,svc,now=configured(tmp_path);calls=[]
    monkeypatch.setattr(engine.email_scheduler.outlook,'send',lambda *a:calls.append(a) or {'status':status})
    action=PendingAction(kind='send',order_id='ORD-005',payload={'recipient':'department@example.com','text':'Reviewed message','department':'PACKING'},preview='review',created_at=now)
    async def run():
        assert (await engine.email_scheduler.send_now(action,now))['status']==status
        await engine.email_scheduler.send_now(action,now)
    asyncio.run(run());assert len(calls)==1 and engine.email_scheduler.history()[0]['status']==status


def test_department_validation():
    with pytest.raises(ValidationError):EmailPreferences(version=0,manager_email='a@example.com',departments={'ASSEMBLY':'bad'})
    with pytest.raises(ValidationError):EmailPreferences(version=0,manager_email='a@example.com',departments={'OTHER':'a@example.com'})
