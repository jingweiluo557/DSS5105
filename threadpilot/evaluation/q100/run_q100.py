"""Run the 100-question × 3-context sheet through the real workflow engine, offline, with two planners:
  fallback  = the keyword planner the product uses when the model is down (ConversationAgent.fallback)
  ideal     = a careful reading of each question (intent + slots), i.e. what the server does when the model reads right
Rows of one Scenario (Q100_SESSION=field: one Field) run in sequence inside one session per context, so follow-ups ("this order", "Go ahead") have context.
Output: answers_<mode>.json with every answer, intent, tools, flags. Usage: python run_q100.py ideal|fallback ; then python grade.py answers_ideal.json
Department e-mail addresses are fixed test values here so drafts resolve a recipient without a mailbox configuration."""
import asyncio, json, os, re, sys, tempfile
from datetime import datetime
from pathlib import Path
B = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(B / 'backend'))
import types
_fake = types.ModuleType('app.services.email_settings')
class EmailSettings:
    def __init__(self, settings): pass
    def read(self): return {'manager_email': 'manager@example.com', 'departments': {d: d.lower() + '@example.com' for d in ('KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING')}}
_fake.EmailSettings = EmailSettings
sys.modules['app.services.email_settings'] = _fake
from app.conversation import ConversationAgent, Plan, Task
from app.schemas import ChatRequest, Classification, DialogState, Intent, Slots
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore
from app.workflow_tools import DataTools
from app.services.order_refs import normalize_order_refs

Q = json.loads(Path(__file__).with_name('questions.json').read_text())
NOW = datetime.fromisoformat('2026-04-01T12:00:00+08:00')

U = lambda reason, **k: dict(intent='general.unanswerable', reason=reason, **k)
# ---- ideal readings. 'ids' = take ORD ids from the (normalised) text; a list = several tasks; 'c2'/'c3' override per context.
A = {
 1: dict(intent='order.risk_overview'),
 2: dict(intent='order.prioritize'),
 3: dict(intent='order.prioritize', window_days=0),
 4: dict(intent='order.summary'),
 5: dict(intent='order.lookup', ids=1),
 6: dict(intent='order.lookup', reference='ambiguous'),
 7: dict(intent='execution.chase', action='draft', quantity=1500, product='tops', c2=dict(intent='order.expedite', quantity=1500, product='tops'), c3=dict(intent='order.expedite', quantity=1500, product='tops')),
 8: dict(intent='order.expedite', stage='WASHING', reference='ambiguous'),
 9: dict(intent='order.expedite', ids=1, c2=dict(intent='execution.chase', action='draft', ids=1), c3=dict(intent='execution.chase', action='draft', ids=1)),
 10: dict(intent='execution.chase', action='draft', reference='active'),
 11: dict(intent='order.refresh', reference='active'),
 12: dict(intent='order.lookup', reference='active'),
 13: dict(intent='order.risk', reference='active', action='recommend'),
 14: dict(intent='operations.output'),
 15: dict(intent='execution.chase', action='draft', reference='ambiguous'),
 16: dict(intent='execution.chase', action='draft', reference='ambiguous', c2=dict(intent='order.expedite', reference='ambiguous'), c3=dict(intent='order.expedite', reference='ambiguous')),
 17: dict(intent='execution.chase', action='draft', customer='Cotton Club', chase_mode='separate', c2=dict(intent='order.expedite', customer='Cotton Club'), c3=dict(intent='order.expedite', customer='Cotton Club')),
 18: dict(intent='order.refresh', ids=1),
 19: dict(intent='order.risk', ids=1, action='evidence'),
 20: dict(intent='order.risk', ids=1, action='explain'),
 21: dict(intent='order.risk', ids=1),
 22: dict(intent='order.rank', criterion='idle_days'),
 23: U('other'),
 24: dict(intent='order.risk', ids=1, action='explain'),
 25: dict(intent='order.rank', criterion='idle_days', window_days=7),
 26: U('other'),
 27: dict(intent='order.prioritize', criterion='risk'),
 28: dict(intent='order.compare', ids=1),
 29: dict(intent='order.compare', reference='ambiguous'),
 30: dict(intent='order.prioritize', stage='WASHING'),
 31: U('other'), 32: U('other'), 33: U('other'), 34: U('other'),
 35: dict(intent='order.compare', ids=1, criterion='risk'),
 36: dict(intent='order.compare', reference='ambiguous'),
 37: dict(intent='order.commitment', quantity=800, product='hoodies', due_date='2026-04-08'),
 38: dict(intent='order.commitment', quantity=600, product='scarves', due_date='2026-04-06'),
 39: dict(intent='order.commitment', product='beanies', due_date='2026-04-07'),
 40: dict(intent='order.commitment', quantity=1200, product='crewneck'),
 41: [dict(intent='order.commitment', quantity=600, product='scarves', due_date='2026-04-06'), dict(intent='order.commitment', quantity=1500, product='cardigans', due_date='2026-04-10')],
 42: dict(intent='order.commitment', quantity=1200, product='crewneck'),
 43: dict(intent='order.commitment', quantity=1200, product='polos', due_date='2026-04-09'),
 44: dict(intent='order.commitment', quantity=800, product='scarves', due_date='2026-04-09'),
 45: dict(intent='order.forecast', quantity=1000, product='hoodies'),
 46: dict(intent='operations.discovery'),
 47: dict(intent='order.prioritize', window_days=0),
 48: dict(intent='order.prioritize', window_days=0),
 49: dict(intent='order.compare', ids=1, comparison_fields=['due_date']),
 50: dict(intent='operations.discovery'),
 51: dict(intent='operations.discovery'),
 52: dict(intent='order.rank', criterion='idle_days'),
 53: dict(intent='order.prioritize', window_days=7),
 54: dict(intent='order.lookup', customer='TrendCart'),
 55: dict(intent='operations.normality', stage='ASSEMBLY', target_date='2026-03-25'),
 56: dict(intent='operations.normality', stage='ASSEMBLY', target_date='2026-03-30'),
 57: dict(intent='operations.normality', stage='WASHING', target_date='2026-03-30', c2=dict(intent='operations.normality', stage='WASHING', target_date='2026-03-30', observed_output=600)),
 58: dict(intent='operations.normality', stage='PACKING', target_date='2026-03-28'),
 59: dict(intent='operations.normality', stage='KNITTING', target_date='2026-03-26'),
 60: dict(intent='operations.normality', stage='ASSEMBLY', observed_output=800),
 61: dict(intent='operations.normality', stage='ASSEMBLY', target_date='2026-03-22', observed_output=0),
 62: dict(intent='operations.normality', stage='WASHING', target_date='2026-03-25', observed_output=900),
 63: dict(intent='operations.output', stage='ASSEMBLY', window_days=7),
 64: dict(intent='operations.deviation', stage='ASSEMBLY', target_date='2026-03-25'),
 65: dict(intent='operations.deviation', stage='ASSEMBLY', action='explain'),
 66: dict(intent='execution.reminder', action='create', ids=1, condition='no_reply', deadline='2026-04-02T12:00'),
 67: dict(intent='execution.reminder', action='create', ids=1, condition='no_activity', deadline='Friday'),
 68: dict(intent='execution.reminder', action='create', reference='active', condition='no_reply', deadline='2026-04-02T12:00'),
 69: dict(intent='execution.reminder', action='create', ids=1, condition='no_reply', deadline='2026-03-31T12:00', c2=dict(intent='execution.reminder', action='create', reference='active', condition='no_reply', deadline='2026-04-01T09:00')),
 70: U('external', ids=1),
 71: dict(intent='execution.reminder', action='create', stage='ASSEMBLY', condition='stage_below_range', deadline='2026-04-02T07:00'),
 72: dict(intent='execution.reminder', action='confirm_target'),
 73: dict(intent='execution.chase', action='draft', ids=1),
 74: dict(intent='execution.chase', action='draft', ids=1, recipient='customer'),
 75: dict(intent='execution.chase', action='draft', customer='TrendCart'),
 76: dict(intent='execution.chase', action='send', ids=1, department='PACKING'),
 77: dict(intent='execution.chase', action='revise', tone='firmer but polite', c2=dict(intent='execution.chase', action='revise', tone='softer'), c3=dict(intent='execution.chase', action='revise', tone='shorter and more polite')),
 78: dict(intent='execution.chase', action='revise', text='add the sales manager in CC', c2=dict(intent='execution.chase', action='revise', recipient='W4 lead'), c3=dict(intent='execution.chase', action='revise', recipient='someone else')),
 79: dict(intent='execution.chase', action='send', ids=1, recipient='W2'),
 80: dict(intent='unknown', confidence=0.4),
 81: dict(intent='execution.chase', action='draft', recipient='W2', text='promise the customer delivery on Friday', c2=U('external'), c3=U('external', ids=1)),
 82: dict(intent='execution.note', action='save', ids=1, text='escalated today', c2=dict(intent='execution.note', action='save', ids=1, text='escalated to the director this morning'), c3=dict(intent='execution.note', action='save', ids=1, text='escalated today')),
 83: dict(intent='execution.chase', action='draft', ids=1, text='how many cartons are left to pack', c2=dict(intent='execution.chase', action='draft', ids=1, department='KNITTING', text='how many pieces can knitting hand over today'), c3=dict(intent='execution.chase', action='draft', ids=1, text='how far along are the scarves; quick update')),
 84: dict(intent='execution.chase', action='revise', deadline='11:30', c2=dict(intent='execution.chase', action='revise', deadline='tomorrow morning'), c3=dict(intent='execution.chase', action='revise', deadline='14:30')),
 85: dict(intent='execution.chase', action='send', ids=1),
 86: dict(intent='execution.chase', action='draft', product='scarves', reference='ambiguous', c2=dict(intent='execution.chase', action='draft', customer='TrendCart'), c3=dict(intent='execution.chase', action='draft', reference='ambiguous')),
 87: dict(intent='execution.chase', action='draft', ids=1, text='expected handoff date with a reason'),
 88: dict(intent='execution.chase', action='read', ids=1),
 89: dict(intent='execution.chase', action='draft', recipient='W4', text='can W4 take 300 pieces next Monday', c2=dict(intent='execution.chase', action='revise', text='if W2 cannot take all 500 pieces, could they take half'), c3=dict(intent='execution.chase', action='draft', recipient='W6', ids=1, text='is Thursday when W6 can receive the batch or finish it')),
 90: dict(intent='execution.chase', action='draft', department='PACKING', text='is packing waiting for cartons', c3=dict(intent='execution.chase', action='draft', ids=1)),
 91: dict(intent='execution.note', action='save', ids=1, text='keep queue position today; review tomorrow 9 a.m.', c2=dict(intent='execution.note', action='save', ids=1, text='stays in sequence until knitting reports the count'), c3=dict(intent='execution.note', action='save', ids=1, text='will not move up during the afternoon shift; revisit at handover')),
 92: dict(intent='execution.note', action='update', reference='active', text='W4 has not confirmed when it can receive the batch', c2=dict(intent='execution.note', action='update', reference='active', text='reason: waiting for inspection results; the customer has not asked for a delay'), c3=dict(intent='execution.note', action='update', reference='active', text='holding off on a Friday completion commitment until night-shift staffing is confirmed')),
 93: dict(intent='execution.note', action='update', ids=1, text='review moved from Tuesday to Thursday', c2=dict(intent='execution.note', action='update', ids=1, text='review time changed from 3 to 3:30 p.m.; rest unchanged'), c3=dict(intent='execution.note', action='update', ids=1, text='pausing outsourcing (corrected order)')),
 94: dict(intent='execution.note', action='save', product='scarf', reference='ambiguous', text='sticking to the plan', c2=dict(intent='execution.note', action='save', customer='TrendCart', reference='ambiguous', text='hold off on changes'), c3=dict(intent='execution.note', action='save', reference='ambiguous', text='revisit next week')),
 95: dict(intent='execution.note', action='save', ids=1, text='holding off outsourcing; revisit if W4 confirms by noon Thursday', c2=dict(intent='execution.note', action='save', ids=1, text='stays in-house for now; reassess outsourcing if 300 pieces are still unfinished tomorrow'), c3=dict(intent='execution.note', action='save', ids=1, text='condition: if W2 can only take half the batch, recalculate the delivery date')),
 96: dict(intent='execution.note', action='save', ids=1, text='20 pieces to be sampled; QC sign-off before release', c2=dict(intent='execution.note', action='save', ids=1, text='handover: reinspection result due tomorrow morning; night shift to hold'), c3=dict(intent='execution.note', action='update', ids=1, text='approved sending for inspection; shipment approval still pending')),
 97: dict(intent='execution.note', action='save', ids=1, text='moving up a day is a suggestion; pending supervisor approval', c2=dict(intent='execution.note', action='save', ids=1, text='discussion note: sending the batch to W6 was suggested; not approved'), c3=dict(intent='execution.note', action='save', reference='active', text='moving to the front was a feasibility question; under review')),
 98: dict(intent='execution.note', action='read', ids=1, c2=dict(intent='execution.note', action='read', reference='active'), c3=dict(intent='execution.note', action='read', ids=1)),
 99: U('people', ids=1),
 100: dict(intent='execution.note', action='save', ids=1, text='handover: verify count this morning; evening supervisor confirms packing time', c2=dict(intent='execution.note', action='update', ids=1, text='handover: I contact W2; Chen follows up with quality control'), c3=dict(intent='execution.note', action='save', ids=1, text='warehouse reports remaining material by 2 p.m., then planning replies')),
}

class IdealPlanner:
    client, degraded, api_style, model = None, True, 'responses', 'ideal'
    def __init__(self): self.spec = None
    async def plan(self, message, state, now):
        specs = self.spec if isinstance(self.spec, list) else [self.spec]
        tasks = []
        for sp in specs:
            sp = {k: v for k, v in sp.items() if k not in ('c2', 'c3')}
            ids = re.findall(r'ORD-\d{3}', message.upper()) if sp.pop('ids', 0) else []
            conf = sp.pop('confidence', .95); intent = Intent(sp.pop('intent'))
            slots = Slots(order_ids=ids, **sp)
            if ids and slots.reference == 'none': slots = slots.model_copy(update={'reference': 'explicit'})
            tasks.append(Task(message=message, classification=Classification(intent=intent, confidence=conf, slots=slots)))
        return Plan(tasks=tasks)
    async def narrate(self, message, state, responses, emit=None): return '\n\n'.join(r.answer for r in responses)
    async def compose_chase(self, request, revision, facts, order_ids, previous, fallback, emit=None, **kw): return fallback

class FallbackPlanner(IdealPlanner):
    model = 'fallback'
    async def plan(self, message, state, now): return ConversationAgent.fallback(message, state)

class Sender:
    def __init__(self): self.sent = []
    async def send(self, payload, key): self.sent.append(payload); return 'r'

class Mailbox:
    """Looks like the email scheduler to the engine (as the live site has one); records sends, delivers nothing."""
    outlook = types.SimpleNamespace(settings=None, missing=lambda: False)
    def __init__(self): self.sent = []
    async def send_now(self, action, now):
        self.sent.append({'recipient': action.payload.get('recipient'), 'subject': action.payload.get('subject')}); return {'status': 'sent', 'receipt': 'test'}

async def run(mode):
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        groups = {}
        key = 'scenario' if os.environ.get('Q100_SESSION', 'scenario') == 'scenario' else 'field'
        for q in Q: groups.setdefault(q[key], []).append(q)
        for ctx in range(3):
            for field, rows in groups.items():
                sender = Sender(); eng = WorkflowEngine(DataTools(B / 'data'), WorkflowStore(Path(tmp) / f'{mode}{ctx}{abs(hash(field))}.db'), lambda: NOW, sender)
                pl = IdealPlanner() if mode == 'ideal' else FallbackPlanner()
                eng.email_scheduler = Mailbox()
                st = DialogState(); eng.store.save(st); conf = None
                for q in rows:
                    msg = q['q'][ctx]
                    if not msg: continue
                    spec = A[q['no']]
                    if isinstance(spec, dict): spec = spec.get(f'c{ctx + 1}', spec)
                    pl.spec = spec
                    sent_before = len(sender.sent) + len(eng.email_scheduler.sent)
                    turns = []
                    try:
                        r = await eng.chat(ChatRequest(message=msg, session_id=st.session_id, confirmation_id=conf), pl)
                        st, conf = r.state, r.confirmation_id
                        turns.append((msg, r.answer))
                        # the product's standard one-question clarifications, answered as a user would
                        for _ in range(2):
                            a = r.answer or ''
                            if r.needs_clarification and 'ready at our factory or delivered' in a:
                                follow, pl.spec = 'Ready at the factory.', dict(intent='order.commitment', delivery_point='factory')
                            elif r.needs_clarification and 'Due today only, or include the next seven days' in a:
                                follow, pl.spec = 'Include the next seven days.', dict(intent='order.prioritize', window_days=7)
                            else: break
                            r = await eng.chat(ChatRequest(message=follow, session_id=st.session_id, confirmation_id=conf), pl)
                            st, conf = r.state, r.confirmation_id
                            turns.append((follow, r.answer))
                        out.append(dict(no=q['no'], ctx=ctx + 1, field=q['field'], q=msg, normalized=normalize_order_refs(msg), intent=str(r.intent), clar=r.needs_clarification, confreq=r.confirmation_required,
                                        selected=r.selected_order_id, tools=[c.name for c in r.tool_calls], sent=len(sender.sent) + len(eng.email_scheduler.sent) - sent_before, turns=turns, answer=r.answer))
                    except Exception as e:
                        out.append(dict(no=q['no'], ctx=ctx + 1, field=q['field'], q=msg, error=f'{type(e).__name__}: {e}', turns=turns, answer=''))
    return out

if __name__ == '__main__':
    mode = sys.argv[1]
    res = asyncio.run(run(mode))
    Path(__file__).with_name(f'answers_{mode}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(mode, len(res), 'answers;', sum(1 for r in res if r.get('error')), 'errors')
