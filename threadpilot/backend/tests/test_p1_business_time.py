import asyncio
from datetime import timedelta
from app.schemas import ChatRequest, Intent, Slots
from app.conversation import ConversationAgent
from app.workflow_tools import resolve_datetime
from .test_conversation import Planned, task
from .test_department_email import configured


def test_multi_order_pronoun_cannot_use_planner_guess(tmp_path):
    engine,_,_=configured(tmp_path)
    async def run():
        r=await engine.chat(ChatRequest(message='Tell me the stage of ORD-005 and ORD-055'),Planned(
            task(Intent.ORDER_REFRESH,'ORD-005',order_ids=['ORD-005']),
            task(Intent.ORDER_REFRESH,'ORD-055',order_ids=['ORD-055'])))
        assert r.selected_order_id is None and r.state.active_order is None
        assert r.state.comparison_orders==['ORD-005','ORD-055']
        r=await engine.chat(ChatRequest(message='Is it late?',session_id=r.state.session_id),
            Planned(task(Intent.ORDER_RISK,'Is ORD-055 late?',order_ids=['ORD-055'],reference='active')))
        assert r.needs_clarification and 'Which order' in r.answer
        assert not r.tool_calls and r.state.active_order is None
        r=await engine.chat(ChatRequest(message='ORD-055',session_id=r.state.session_id),
            Planned(task(Intent.ORDER_RISK,'ORD-055',order_ids=['ORD-055'])))
        assert not r.needs_clarification and r.selected_order_id=='ORD-055'
    asyncio.run(run())


def test_missing_new_department_address_never_reuses_old(tmp_path):
    from app.services.email_settings import EmailPreferences
    engine,svc,_=configured(tmp_path)
    prefs=svc.preferences.read();prefs['departments']['ASSEMBLY']=''
    svc.preferences.save(EmailPreferences(**prefs))
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Preview draft 1 for Assembly instead',session_id=r.state.session_id),
            Planned(task(Intent.EXECUTION_CHASE,action='send',draft_number=1,department='ASSEMBLY')))
        assert not r.confirmation_required and r.needs_clarification
        assert not r.state.chase_drafts[0]['recipient']
    asyncio.run(run())


def test_reply_deadline_frozen_across_review_and_day_change(tmp_path):
    engine,_,now=configured(tmp_path);clock=[now];engine.clock=lambda:clock[0]
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Ask for an answer by tomorrow noon.',session_id=r.state.session_id),
            Planned(task(Intent.EXECUTION_CHASE,action='revise',deadline='tomorrow noon')))
        assert r.state.chase_drafts[0]['reply_deadline']=='2026-04-02T12:00:00+08:00'
        assert '2026-04-02T12:00:00+08:00' in r.state.chase_drafts[0]['text']
        clock[0]+=timedelta(days=1)
        r=await engine.chat(ChatRequest(message='Preview draft 1',session_id=r.state.session_id),ConversationAgent(None))
        assert r.state.pending_action.payload['reply_deadline']=='2026-04-02T12:00:00+08:00'
        assert '2026-04-03' not in r.answer
    asyncio.run(run())


def test_repeated_preview_does_not_postpone_send_time(tmp_path):
    engine,_,now=configured(tmp_path);clock=[now];engine.clock=lambda:clock[0]
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Send draft 1 in 2 minutes',session_id=r.state.session_id),ConversationAgent(None))
        due=r.state.pending_action.payload['send_at']
        clock[0]+=timedelta(seconds=50)
        r=await engine.chat(ChatRequest(message='Preview draft 1',session_id=r.state.session_id),ConversationAgent(None))
        assert r.state.pending_action.payload['send_at']==due==(now+timedelta(minutes=2)).isoformat()
    asyncio.run(run())


def test_priority_clock_and_window_cannot_be_renarrated(tmp_path):
    engine,_,now=configured(tmp_path)
    async def run():
        agent=Planned(task(Intent.ORDER_PRIORITIZE,window_days=7))
        # Any accidental call to the provider here would fail.
        agent.client=object()
        r=await engine.chat(ChatRequest(message='What needs attention in seven days?'),agent)
        # the business date and the window are stated verbatim in the server's own words (26 Oct wording)
        assert 'business date 2026-04-01' in r.answer
        assert 'for 2026-04-01 to 2026-04-08' in r.answer
        tool=next(t for t in r.tool_calls if t.name=='prioritize_orders')
        assert tool.result['business_now']==now.isoformat()
    asyncio.run(run())


def test_iso_time_precision_and_timezone_use_business_zone(tmp_path):
    _,_,now=configured(tmp_path)
    result=resolve_datetime('2026-04-02T04:00:00.123456+00:00',now)
    assert result.isoformat()=='2026-04-02T12:00:00.123456+08:00'
    assert resolve_datetime('Friday morning',now) is None


def test_clock_reset_requires_new_draft(tmp_path):
    from app.business_clock import BusinessClock
    engine,_,now=configured(tmp_path)
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        BusinessClock(engine.email_scheduler.outlook.settings).save('demo',now,0)
        r=await engine.chat(ChatRequest(message='Preview draft 1',session_id=r.state.session_id),ConversationAgent(None))
        assert r.needs_clarification and not r.confirmation_required
        assert 'Business clock changed' in r.answer
    asyncio.run(run())
