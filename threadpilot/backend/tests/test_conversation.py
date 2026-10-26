import asyncio
import pytest
from types import SimpleNamespace

from app.conversation import ConversationAgent, Plan, Task
from app.schemas import ChatRequest, Classification, Intent, Slots
from app.services.snapshot_service import DatabaseDataTools
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore
from app.workflow_tools import resolve_date
from .test_workflow import NOW


class Planned(ConversationAgent):
    def __init__(self, *tasks):
        super().__init__(None)
        self.tasks = tasks

    async def plan(self, *args):
        return Plan(tasks=list(self.tasks))


def task(intent, message='', resume=False, **slots):
    return Task(message=message, resume=resume, classification=Classification(
        intent=intent, confidence=1, slots=Slots(**slots)))


def test_counts_switch_resume_and_multirequest(tmp_path, business_database):
    engine = WorkflowEngine(DatabaseDataTools(business_database), WorkflowStore(tmp_path/'chat.db'), lambda:NOW)
    async def run():
        first = await engine.chat(ChatRequest(message='800 hoodies in 10 working days'), Planned(task(
            Intent.ORDER_COMMITMENT, '800 hoodies in 10 working days', product='hoodies',quantity=800,due_date='in 10 working days')))
        assert first.needs_clarification
        session = first.state.session_id
        second = await engine.chat(ChatRequest(message='How many orders are in PACKING?',session_id=session),
            Planned(task(Intent.ORDER_SUMMARY,stage='PACKING'),task(Intent.GENERAL)))
        actual = sum(r.record['current_stage']=='PACKING' for r in engine.tools.rows('orders.csv'))
        assert second.tool_calls[0].result['total_orders']==actual
        assert second.selected_order_id is None
        third = await engine.chat(ChatRequest(message='delivered to the customer',session_id=session),
            Planned(task(Intent.ORDER_COMMITMENT,'delivered to the customer',True,delivery_point='customer')))
        assert not third.needs_clarification
        assert third.slots.quantity == 800 and third.slots.product=='hoodies'
        assert any(t.name=='estimate_capacity' for t in third.tool_calls)
        # A different business topic then an explicit resume restores missing slots.
        await engine.chat(ChatRequest(message='Open ORD-058',session_id=session),
            Planned(task(Intent.ORDER_LOOKUP,'Open ORD-058',order_ids=['ORD-058'])))
        fourth = await engine.chat(ChatRequest(message='back to the new order, lose one packing day',session_id=session),
            Planned(task(Intent.ORDER_COMMITMENT,'lose one packing day',True,packing_loss_days=1)))
        assert fourth.slots.quantity==800 and fourth.slots.packing_loss_days==1
    asyncio.run(run())


def test_true_provider_deltas_and_failure(tmp_path, business_database):
    class Stream:
        closed=False
        async def __aiter__(self):
            yield SimpleNamespace(type='response.output_text.delta',delta='Hello')
            await asyncio.sleep(0)
            yield SimpleNamespace(type='response.output_text.delta',delta=' there')
            yield SimpleNamespace(type='response.completed')
        async def close(self):
            self.closed=True
    stream=Stream()
    async def create(**kwargs):
        assert kwargs['stream'] is True
        return stream
    agent=Planned(task(Intent.GENERAL))
    agent.client=SimpleNamespace(responses=SimpleNamespace(create=create))
    engine=WorkflowEngine(DatabaseDataTools(business_database),WorkflowStore(tmp_path/'chat.db'),lambda:NOW)
    chunks=[]
    async def emit(chunk):
        chunks.append(chunk)
        if chunk=='Hello':
            assert not stream.closed
    result=asyncio.run(engine.chat(ChatRequest(message='Hi'),agent,emit))
    assert chunks==['Hello',' there'] and result.answer=='Hello there' and stream.closed
    assert engine.store.load(result.state.session_id).history[-1]['content']=='Hello there'


def test_working_days_and_fallback():
    assert resolve_date('in 10 working days',NOW).isoformat()=='2026-04-13'
    assert ConversationAgent.fallback('How many orders in PACKING?').tasks[0].classification.slots.stage=='PACKING'


def test_multiple_orders_are_scoped_per_task(tmp_path,business_database):
    engine=WorkflowEngine(DatabaseDataTools(business_database),WorkflowStore(tmp_path/'chat.db'),lambda:NOW)
    message='Tell me the stages of ORD-058 and ORD-005 and explain bottlenecks'
    agent=Planned(task(Intent.ORDER_REFRESH,message,order_ids=['ORD-058','ORD-005']),task(Intent.GENERAL))
    response=asyncio.run(engine.chat(ChatRequest(message=message),agent))
    assert {t.arguments.get('order_id') for t in response.tool_calls if t.name=='refresh_order'}=={'ORD-058','ORD-005'}
    assert not response.needs_clarification


def test_cancelled_stream_does_not_save_partial_turn(tmp_path, business_database):
    class Interrupted(Planned):
        async def narrate(self, message, state, responses, emit=None):
            await emit('partial')
            raise asyncio.CancelledError()
    engine=WorkflowEngine(DatabaseDataTools(business_database),WorkflowStore(tmp_path/'chat.db'),lambda:NOW)
    async def run():
        initial=await engine.chat(ChatRequest(message='Open ORD-005'),Planned(task(Intent.ORDER_LOOKUP,'Open ORD-005')))
        session=initial.state.session_id
        async def emit(text):
            assert text=='partial'
        with pytest.raises(asyncio.CancelledError):
            await engine.chat(ChatRequest(message='Hi',session_id=session),Interrupted(task(Intent.GENERAL)),emit)
        assert engine.store.load(session).history==initial.state.history
        assert not engine.lock.locked()
    asyncio.run(run())


def test_topic_change_revokes_execution_confirmation(tmp_path, business_database):
    engine=WorkflowEngine(DatabaseDataTools(business_database),WorkflowStore(tmp_path/'chat.db'),lambda:NOW)
    async def run():
        preview=await engine.chat(ChatRequest(message='Add note to ORD-005: check progress'),
            Planned(task(Intent.EXECUTION_NOTE,'Add note to ORD-005: check progress',text='check progress')))
        assert preview.confirmation_required
        session=preview.state.session_id
        await engine.chat(ChatRequest(message='what is efficiency',session_id=session),Planned(task(Intent.GENERAL)))
        result=await engine.chat(ChatRequest(message='确认',session_id=session,confirmation_id=preview.confirmation_id),Planned(task(Intent.GENERAL)))
        assert 'No matching pending action' in result.answer
        assert engine.store.action_result(preview.confirmation_id,session) is None
    asyncio.run(run())
