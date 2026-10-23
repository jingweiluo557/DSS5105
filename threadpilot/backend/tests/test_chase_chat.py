"""Recipient, selection and per-draft confirmation boundaries."""
import asyncio
from app.conversation import ConversationAgent
from app.schemas import ChatRequest, DialogState
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore
from app.workflow_tools import DataTools
from .test_workflow import DATA, NOW


def test_chase_modes_recipients_and_confirmations(tmp_path):
    engine = WorkflowEngine(DataTools(DATA), WorkflowStore(tmp_path/'chat.db'), lambda:NOW)
    agent = ConversationAgent(None)
    sent = []
    class Sender:
        async def send(self, payload, key):
            sent.append(payload)
            return 'test-receipt'
    engine.sender = Sender()
    async def run():
        state = DialogState(active_order='ORD-020', last_order_ids=['ORD-020'])
        engine.store.save(state)
        async def ask(text, confirmation=None):
            return await engine.chat(ChatRequest(message=text,session_id=state.session_id,confirmation_id=confirmation), agent)
        r = await ask('Draft a chase-up for ORD-002 and ORD-005')
        assert r.order_ids == ['ORD-002','ORD-005'] and r.selected_order_id is None
        assert r.state.pending_clarification.candidates == r.order_ids
        assert 'summary draft or separate' in r.answer and 'As of' not in r.answer
        r = await ask('separate drafts')
        assert len(r.state.chase_drafts) == 2 and not sent
        r = await ask('send draft 2')
        assert r.needs_clarification and not r.confirmation_required
        r = await ask('manager@example.com')
        assert r.confirmation_required and 'ORD-005' in r.answer and not sent
        r = await ask('send now', r.confirmation_id)
        assert len(sent) == 1 and sent[0]['order_ids'] == ['ORD-005']
        assert r.state.chase_drafts[1]['sent'] and not r.state.chase_drafts[0]['sent']
        r = await ask('Draft a chase-up for ORD-002')
        assert 'Who should receive' in r.answer and 'tone' not in r.answer
        assert not r.state.chase_drafts
        r = await ask('Draft one summary chase-up to myself for ORD-002 and ORD-005')
        assert len(r.state.chase_drafts) == 1 and r.state.chase_drafts[0]['recipient']=='self'
        assert not r.confirmation_required and len(sent)==1
        r = await ask('send draft 1')
        assert 'email address' in r.answer and not r.confirmation_required
    asyncio.run(run())

def test_chase_provider_stream_and_partial_failure(tmp_path):
    from types import SimpleNamespace
    from app.schemas import Classification, Intent, Slots
    from .test_conversation import Planned, task
    engine = WorkflowEngine(DataTools(DATA), WorkflowStore(tmp_path/'stream.db'), lambda:NOW)
    class Stream:
        failed = False
        closed = False
        async def __aiter__(self):
            yield SimpleNamespace(type='response.output_text.delta',delta='Please verify ')
            await asyncio.sleep(0)
            yield SimpleNamespace(type='response.output_text.delta',delta='ORD-002.')
            if not self.failed:
                yield SimpleNamespace(type='response.completed')
        async def close(self):
            self.closed=True
    stream = Stream()
    async def create(**kwargs):
        assert kwargs['stream'] is True
        return stream
    agent = Planned(task(Intent.EXECUTION_CHASE, order_ids=['ORD-002'], action='draft', chase_mode='summary'))
    agent.client=SimpleNamespace(responses=SimpleNamespace(create=create))
    pieces=[]
    async def emit(chunk):
        if chunk=='Please verify ':
            assert not stream.closed
        pieces.append(chunk)
    async def run():
        response=await engine.chat(ChatRequest(message='Summary chase-up for ORD-002'),agent,emit)
        assert ''.join(pieces)==response.answer
        assert 'Please verify ' in pieces and 'ORD-002.' in pieces
        assert response.state.chase_drafts[0]['text']=='Please verify ORD-002.'
        stream.failed=True
        stream.closed=False
        import pytest
        with pytest.raises(ValueError,match='interrupted'):
            await engine.chat(ChatRequest(message='Summary chase-up for ORD-002',session_id=response.state.session_id),agent,emit)
        assert engine.store.load(response.state.session_id).chase_drafts==response.state.chase_drafts
    asyncio.run(run())
