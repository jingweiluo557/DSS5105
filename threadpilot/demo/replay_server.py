"""Offline replay server for the demo recording: the real frontend and the real workflow engine over the CSV seeds,
with a scripted planner instead of the language model, so the demo can be recorded anywhere (a GitHub runner, a
laptop) without the deployed site, an access key or a model key.

    python demo/replay_server.py [port]            # default 8765; serves threadpilot/frontend and the API the pages use

What is real: every tool, the queue engine, the alert policy, the home screen, the dialogue rules (ask, don't guess;
context; preview and confirm; watches), the evidence rows. What is replaced: the planner (a table of classifications
for the demo's questions, the same annotations the offline evaluation uses; anything else falls back to the keyword
planner) and the narrator (the server's own answer is shown, JSON blocks turned into a sentence). Nothing is sent:
the mailbox is a stub and the department addresses are examples. The recording's captions say "offline replay".
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import types
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.chdir(ROOT / 'frontend')

# The mailbox settings module needs the Outlook stack; the replay never sends, so a stub with example addresses is enough.
_fake = types.ModuleType('app.services.email_settings')


class EmailSettings:  # noqa: D101
    def __init__(self, settings):
        pass

    def read(self):
        return {'manager_email': 'manager@example.com', 'departments': {d: d.lower() + '@example.com' for d in ('KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING')}}


_fake.EmailSettings = EmailSettings
sys.modules['app.services.email_settings'] = _fake

from app.conversation import ConversationAgent, Plan, Task  # noqa: E402
from app.prediction.aft import LeadTimeModel  # noqa: E402
from app.schemas import ChatRequest, Classification, Intent, Slots  # noqa: E402
from app.services import alert_policy, home_service  # noqa: E402
from app.services.queue_engine import QueueAnalysis  # noqa: E402
from app.workflow_engine import WorkflowEngine  # noqa: E402
from app.workflow_store import WorkflowStore  # noqa: E402
from app.workflow_tools import DataTools  # noqa: E402

NOW = datetime.fromisoformat(os.environ.get('REPLAY_NOW', '2026-04-01T09:00:00+08:00'))
tools = DataTools(ROOT / 'data')
data, _ = tools.queue_snapshot(NOW)
for name in ('orders', 'production_log', 'workshops'):
    for i, r in enumerate(data[name]):
        r['_record_id'] = i + 1
        r['_version'] = 1
snapshot = {'today': data['today'], 'generated_at': NOW.isoformat(), **{k: data[k] for k in ('orders', 'production_log', 'workshops')}}
queue = QueueAnalysis(data)
risk = queue.summary()
model = LeadTimeModel()
for row in risk['orders']:
    f = model.forecast_order(row, NOW.date())
    row['forecast'] = {k: f[k] for k in ('delay_probability', 'expected_completion_date', 'completion_range_80pct', 'typical_lead_days_for_this_size')}
home = home_service.home(data, NOW)
alerts = alert_policy.summarize(alert_policy.gate(alert_policy.detect(data, NOW), [], NOW))


def _d(iso):
    return datetime.fromisoformat(iso + 'T00:00:00').strftime('%-d %b')


def write_briefing():
    """The 07:00 briefing without a model: the same three sections the live model writes, filled from the home
    screen's own facts (the live site's model is grounding-checked against the same packet), so nothing on screen disagrees."""
    pulse = {r['stage']: r for r in home['pulse']}
    below = [r for r in home['pulse'] if r['status'] == 'below']
    within = [r for r in home['pulse'] if r['status'] != 'below']
    day = home['pulse'][0]['date']
    if below:
        b = below[0]
        yesterday = (f"On {_d(day)} {b['stage'].lower()} made {b['pieces']:,} pieces against a normal range of {b['band']['min']:,}–{b['band']['max']:,}, "
                     f"below range for {b['below_days']} working days in a row; " + ', '.join(f"{r['stage'].lower()} ({r['pieces']:,})" for r in within) + ' were within range.')
    else:
        yesterday = f"On {_d(day)} every stage was within its normal range."
    overdue = sorted((r for r in risk['orders'] if r['risk']['level'] == 'overdue'), key=lambda r: -r['risk']['days_past_due'])
    top = [f"{len(overdue)} orders are overdue; the oldest are " + ' and '.join(f"{r['order_id']} ({r['customer']}, {r['risk']['days_past_due']} days)" for r in overdue[:2]) + '.']
    for b in below:
        card = next((c for c in home['decisions'] if c['kind'] == 'stage_drop' and c['entity'] == b['stage']), None)
        waiting = f"; {card['lines'][1][0].lower()}{card['lines'][1][1:]}" if card and len(card['lines']) > 1 else ''
        top.append(f"{b['stage'].title()} is {abs(b['change_pct'])}% under its normal range since {_d(b['below_since'])}{waiting}. The log records no cause.")
    decide = []
    for card in home['decisions']:
        if card['kind'] == 'stage_drop':
            decide.append(f"Ask the floor what changed at {card['entity'].lower()} and when it recovers.")
        elif card['kind'] == 'will_miss':
            o = next(r for r in risk['orders'] if r['order_id'] == card['entity'])
            decide.append(f"Expedite, outsource or re-date {o['order_id']} ({o['customer']}): due {_d(o['due_date'])}, best case {_d(o['risk']['best_date'])}.")
    return {'yesterday': yesterday, 'top_issue': '\n'.join('- ' + t for t in top), 'decide': '\n'.join('- ' + t for t in decide)}


_brief = write_briefing()
BRIEFING = {'id': 'r1', 'day': data['today'], 'business_date': data['today'], 'generated_at': NOW.replace(hour=7, minute=0).isoformat(),
            'model': 'offline replay (scripted, no model)', 'generation_version': 'morning-v8-dashboard-actions-decisions', 'fingerprint': 'replay',
            'latest_production_date': home['pulse'][0]['date'], **_brief,
            'production_note': 'Normal range = the previous eight same-weekday records per stage; the factory is closed on Sundays.',
            'sections': {k: {'text': v, 'evidence': ['home']} for k, v in {**_brief, 'production_note': 'Normal range = the previous eight same-weekday records.'}.items()},
            'facts': {'home': {'status': home['status'], 'pulse': home['pulse'], 'counts': home['counts']},
                      'counts': {'in_progress': home['counts']['in_progress'], 'overdue': home['counts']['overdue'],
                                 'high': sum(r['risk']['level'] == 'high' for r in risk['orders']), 'medium': sum(r['risk']['level'] == 'medium' for r in risk['orders'])},
                      'yesterday': {'records_available': True, 'stage_completions': sum(r['pieces'] or 0 for r in home['pulse'])}}}
TASKS = [{'id': 'manual:1', 'order_id': None, 'title': 'Call Northwind about the beanie delivery', 'origin': 'manual', 'done': False, 'version': 1, 'reasons': []}]
TASKS += [{'id': f'ai:{i}', 'order_id': (re.findall(r'ORD-\d+', t) or [None])[0], 'title': t, 'origin': 'ai', 'done': False, 'version': 1, 'reasons': ['AI recommendation']}
          for i, t in enumerate(l[2:] for l in _brief['decide'].splitlines())]
DASHBOARD = {'business_date': data['today'], 'counts': home['counts'], 'health': home['health'], 'tasks': TASKS, 'ai_briefing': BRIEFING,
             'history': [], 'advice': [], 'orders': [], 'production': [], 'briefings': [], 'forecast': {'available': False}}


# ---------------------------------------------------------------- the scripted planner: the demo's questions, classified
def _key(text: str) -> str:
    return re.sub(r'[^a-z0-9 ]+', '', text.casefold()).strip()


SCRIPT = {
    'how is the trendcart order doing': dict(intent='order.lookup', customer='TrendCart'),
    'the scarf one': dict(intent='order.lookup', product='Scarf'),
    'the scarf order': dict(intent='order.lookup', product='Scarf'),
    'is it already late': dict(intent='order.risk', reference='active'),
    'why would you flag it': dict(intent='order.risk', reference='active', action='explain'),
    'why is it at risk': dict(intent='order.risk', reference='active', action='explain'),
    'can we take 800 hoodies by the 25th': dict(intent='order.commitment', quantity=800, product='hoodies', due_date='25th'),
    'delivered to the customer': dict(intent='order.commitment', delivery_point='customer'),
    'ready at the factory': dict(intent='order.commitment', delivery_point='factory'),
    'what if packing loses a day': dict(intent='order.commitment', packing_loss_days=1),
    'preview draft 1': dict(intent='execution.chase', action='send', draft_number=1),
    'that order hasnt moved in a week chase it up': dict(intent='execution.chase', reference='active', action='draft'),
    'it hasnt moved for a week chase it up': dict(intent='execution.chase', reference='active', action='draft'),
    'chase it up': dict(intent='execution.chase', reference='active', action='draft'),
    'remind me tomorrow if packing is still behind': dict(intent='execution.reminder', stage='PACKING', deadline='tomorrow', condition='stage_below_range'),
    'what revenue did the trendcart orders bring in this quarter': dict(intent='general.unanswerable', reason='money'),
    'which orders are most at risk': dict(intent='order.summary'),
    'did anything go wrong yesterday': dict(intent='operations.discovery'),
    'was yesterdays assembly output normal': dict(intent='operations.normality', stage='ASSEMBLY', target_date='yesterday'),
}


class ScriptedAgent:
    """Stands in for the model: classification from the table, narration = the server's answer made readable."""
    client = None
    degraded = True
    api_style = 'responses'
    model = 'offline replay'

    async def plan(self, message, state, now):
        spec = dict(SCRIPT.get(_key(message), {}))
        lower = message.casefold()
        if not spec and re.search(r'chase-?up to the (\w+) department', lower):
            dept = re.search(r'chase-?up to the (\w+) department', lower)[1].upper()
            spec = dict(intent='execution.chase', action='draft', chase_mode='summary', department=dept)
        if not spec:
            return ConversationAgent.fallback(message, state)
        intent = Intent(spec.pop('intent'))
        return Plan(tasks=[Task(message=message, classification=Classification(intent=intent, confidence=0.95, slots=Slots(**spec)))])

    async def narrate(self, message, state, responses, emit=None):
        return '\n\n'.join(readable(r) for r in responses)

    async def compose_chase(self, request, revision, facts, order_ids, previous, fallback, emit=None, **kwargs):
        # a plain draft from the record, the way the model would word it live
        if len(facts) != 1:
            return fallback
        o = facts[0]
        idle = (NOW.date() - datetime.fromisoformat(o['last_activity_date'] + 'T00:00:00').date()).days
        stage = o['current_stage'].lower()
        text = (f"Hi {stage} team,\n\n{o['order_id']} ({o['customer']}, {int(float(o['pieces'])):,} {o['product'].lower()}) is at {stage} and has shown no recorded activity since "
                f"{o['last_activity_date']} ({idle} days). It is due {o['due_date']}.\n\nPlease confirm by tomorrow noon: the current status, what is holding it, and the date {stage} will finish.\n\nThank you.")
        if emit:
            await emit(text)
        return text


def readable(response) -> str:
    """The narrator's job without a model: keep the prose, turn the JSON blocks into a sentence."""
    text = response.answer
    data = response.tool_calls[-1].result if response.tool_calls else {}
    if 'Conditional forecast, not a promise' in text and 'queue_projection' in data:
        q, h = data['queue_projection'], data.get('historical_lead_time_model') or {}
        cap = q.get('capacity_per_day') or {}
        bottleneck = min(cap, key=cap.get) if cap else None
        best, exp = q.get('best_case', {}), q.get('expected_case', {})
        lines = [f"**{q.get('verdict', 'estimate').title()}** by {data['due_date']} ({data['delivery_point']}): {q.get('reason', '')}",
                 f"Best case finish {best.get('finish_date')}; expected {exp.get('finish_date')} if new orders keep arriving; {q.get('orders_ahead')} orders ahead in the queue."]
        if h:
            lines.append(f"Lead-time model: {int(round(100 * h['p_on_time']))}% on-time chance for {h['pieces']} pieces (typically {h['typical_lead_days']} days; 80% done within {h['lead_days_80pct_confidence']}).")
        if bottleneck:
            lines.append(f"Bottleneck stage: {bottleneck.lower()} at {cap[bottleneck]:,.0f} pieces a day. Packing loss assumed: {data.get('packing_loss_days', 0)} day(s); delivery buffer {data.get('delivery_buffer_days', 0)} days.")
        lines.append('An estimate with stated assumptions, not a promise.')
        return '\n'.join(lines)
    # drop the labelled JSON blocks the model would otherwise word
    text = re.sub(r'\n(?:Facts and risk interpretation|Recorded facts and labelled interpretation|Conditional forecast, not a promise):\n\{[\s\S]*?\n\}', '', text)
    text = re.sub(r'\n\{[\s\S]*\}\s*$', '', text)
    return text.strip()


def feasibility_estimate(body):
    """POST /api/feasibility/estimate, as app/api/feasibility_api.py: the chat's estimate_capacity tool plus chart rows."""
    from app.workflow_tools import resolve_date
    try:
        from app.api.feasibility_api import chart_rows
    except Exception:  # noqa: BLE001  (the API module needs FastAPI's router; the rows function is all we use)
        chart_rows = _chart_rows
    qty = int(body['quantity'])
    slots = Slots(quantity=qty, product=body['product'], due_date=resolve_date(body['due_date'], NOW).isoformat(),
                  delivery_point=body.get('delivery_point') or 'factory', packing_loss_days=body.get('packing_loss_days'), delivery_buffer_days=body.get('delivery_buffer_days'))
    est, evidence = tools.capacity(slots, NOW)
    return {'business_date': data['today'], 'request': slots.model_dump(exclude_none=True), 'estimate': est, 'chart': chart_rows(est, qty), 'evidence_count': len(evidence)}


def _chart_rows(data_, quantity):
    import ast
    src = (ROOT / 'backend/app/api/feasibility_api.py').read_text()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == 'chart_rows')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'feasibility_api', 'exec'), ns)
    return ns['chart_rows'](data_, quantity)


class RecordingSender:
    async def send(self, payload, idempotency_key):
        return 'replay-receipt'


engine = WorkflowEngine(tools, WorkflowStore(Path(tempfile.mkdtemp()) / 'replay.sqlite3'), lambda: NOW, RecordingSender())
class ReplayMailbox:
    """Looks like the email scheduler to the engine; records the send locally and sends nothing."""
    outlook = types.SimpleNamespace(settings=None, missing=lambda: False)
    sent = []

    async def send_now(self, action, now):
        self.sent.append({'recipient': action.payload.get('recipient'), 'subject': action.payload.get('subject'), 'at': now.isoformat()})
        return {'status': 'sent', 'receipt': 'replay-receipt', 'note': 'offline replay: recorded, not delivered'}


engine.email_scheduler = ReplayMailbox()
agent = ScriptedAgent()
lock = asyncio.Lock()


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, body, status=200):
        raw = json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def route(self, path):
        if path == '/api/snapshot': return snapshot
        if path == '/api/email/clock': return {'now': NOW.isoformat(), 'mode': 'legacy', 'version': 1, 'schedule_start_day': data['today']}
        if path == '/api/scheduling/risk': return risk
        if path == '/api/dashboard/home': return home
        if path == '/api/dashboard': return DASHBOARD
        if path == '/api/morning': return {'business_date': data['today'], 'reports': [BRIEFING], 'current_fingerprint': 'replay', 'model_configured': False}
        if path == '/api/v1/health': return {'status': 'ok', 'configured': True, 'model': 'offline replay', 'streaming': True}
        if path == '/api/v1/whoami': return {'role': 'manager'}
        if path == '/api/alerts/preview': return {**alerts, 'emails_enabled': False}
        if path == '/api/predictions': return {'business_date': data['today'], 'imported_at': NOW.isoformat(), 'rows': []}
        if path == '/api/email/settings': return {'clock': {'now': NOW.isoformat(), 'mode': 'legacy', 'version': 1}, 'connection': {'connected': True, 'account': 'manager@example.com'},
                                                 'preferences': {'version': 1, 'manager_email': 'manager@example.com', 'manager_name': 'Manager', 'briefing_enabled': True, 'start_day': data['today'], 'customers': [],
                                                                 'departments': {d: d.lower() + '@example.com' for d in ('KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING')}}}
        if path == '/api/email/activity': return {'entries': []}
        if path.startswith('/api/scheduling/history'): return []
        if path.startswith('/api/v1/workflow/reminders'): return {'reminders': [r for r in engine.store.list_reminders()] if hasattr(engine.store, 'list_reminders') else []}
        return None

    def do_GET(self):
        path = urlparse(self.path).path
        body = self.route(path)
        if body is not None: return self.send_json(body)
        if path.startswith('/api/'): return self.send_json({'error': {'code': 'NOT_FOUND', 'message': 'replay'}}, 404)
        if path == '/': self.path = '/index.html'
        return super().do_GET()

    def stream_chat(self):
        n = self.headers.get('Content-Length'); body = json.loads(self.rfile.read(int(n or 0)) or b'{}')
        self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Cache-Control', 'no-cache'); self.end_headers()

        def ev(kind, payload):
            self.wfile.write(f"event: {kind}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n".encode()); self.wfile.flush()
        ev('start', {'request_id': 'replay'})
        try:
            request = ChatRequest(**{k: v for k, v in body.items() if k in ('message', 'session_id', 'confirmation_id', 'selected_order_id', 'review_draft_id') and v})
            async def emit(text, kind='delta', **detail):
                if kind == 'step':          # the tool-call steps stream live, as on the deployed site
                    ev('step', {'text': text, **detail})
            response = asyncio.run(engine.chat(request, agent, emit=emit))
            payload = response.model_dump(mode='json')
            payload['model'] = 'offline replay'
            ev('facts', {'text': payload['answer']})
            ev('done', payload)
        except Exception as error:  # noqa: BLE001
            ev('error', {'message': f'{type(error).__name__}: {error}', 'request_id': 'replay'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/v1/workflow/chat/stream': return self.stream_chat()
        if path == '/api/feasibility/estimate':
            n = self.headers.get('Content-Length'); body = json.loads(self.rfile.read(int(n or 0)) or b'{}')
            return self.send_json(feasibility_estimate(body))
        if path == '/api/dashboard/tasks':
            n = self.headers.get('Content-Length'); body = json.loads(self.rfile.read(int(n or 0)) or b'{}')
            TASKS.insert(0, {'id': 'manual:' + str(body.get('id', len(TASKS))), 'order_id': None, 'title': body.get('title', ''), 'origin': 'manual', 'done': False, 'version': 1, 'reasons': []})
            return self.send_json({'id': TASKS[0]['id']}, 201)
        if path.startswith('/api/scheduling/orders/') and path.endswith('/draft'):
            oid = path.split('/')[4]
            return self.send_json({'id': 'draft-1', 'review_id': 'review-1', 'order_id': oid, 'version': 1, 'analysis': queue.expedite(oid), 'candidate': '', 'status': 'ready', 'instruction': '', 'text': '', 'reviewer': '', 'decision': 'save', 'stale': False})
        return self.send_json({'error': {'code': 'NOT_FOUND', 'message': 'replay'}}, 404)

    def do_PUT(self):
        n = self.headers.get('Content-Length'); self.rfile.read(int(n or 0))
        return self.send_json({'ok': True})


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f'replay on http://127.0.0.1:{port} · business date {data["today"]} · scripted planner, no model, nothing sent', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
