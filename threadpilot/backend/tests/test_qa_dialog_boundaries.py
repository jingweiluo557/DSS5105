"""Audit expectations: failures deliberately expose current product gaps."""
import asyncio
from app.schemas import ChatRequest, Intent
from app.conversation import ConversationAgent
from .test_department_email import configured
from .test_conversation import Planned, task

def test_separate_drafts_keep_each_departments_recipient(tmp_path):
    engine,_,_=configured(tmp_path)
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Separate drafts for ORD-005 and ORD-055',session_id=r.state.session_id),
            Planned(task(Intent.EXECUTION_CHASE,action='revise',order_ids=['ORD-005','ORD-055'],chase_mode='separate')))
        assert [(d['department'],d['recipient']) for d in r.state.chase_drafts]==[('KNITTING','knitting@example.com'),('ASSEMBLY','assembly@example.com')]
    asyncio.run(run())

def test_department_change_in_preview_changes_recipient(tmp_path):
    engine,_,_=configured(tmp_path)
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Preview draft 1 for Assembly instead',session_id=r.state.session_id),
            Planned(task(Intent.EXECUTION_CHASE,action='send',draft_number=1,department='ASSEMBLY')))
        assert r.state.pending_action.payload['recipient']=='assembly@example.com'
        assert r.state.pending_action.payload['department']=='ASSEMBLY'
    asyncio.run(run())

def test_fallback_cancel_does_not_offer_send_confirmation(tmp_path):
    engine,_,_=configured(tmp_path)
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Preview draft 1',session_id=r.state.session_id),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Cancel, do not send.',session_id=r.state.session_id),ConversationAgent(None))
        assert not r.confirmation_required
    asyncio.run(run())

def test_chase_uses_new_active_order_after_topic_switch(tmp_path):
    engine,_,_=configured(tmp_path)
    async def run():
        r=await engine.chat(ChatRequest(message='Draft a chase-up for ORD-005'),ConversationAgent(None))
        r=await engine.chat(ChatRequest(message='Open ORD-055',session_id=r.state.session_id),
            Planned(task(Intent.ORDER_LOOKUP,'Open ORD-055',order_ids=['ORD-055'])))
        assert r.state.active_order=='ORD-055'
        r=await engine.chat(ChatRequest(message='Draft a chase-up for this order',session_id=r.state.session_id),
            Planned(task(Intent.EXECUTION_CHASE,action='draft',reference='active')))
        assert r.state.chase_drafts[0]['order_ids']==['ORD-055']
    asyncio.run(run())
