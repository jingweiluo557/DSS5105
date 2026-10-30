"""Sprint 3: several orders in one chat, tool calls shown while answering, the measured reason for "8 same weekdays",
the same-day excursion alert with the manager's switch, and voice input. They use scripted planners, so they test the
deterministic server, not the language model."""
import asyncio
import json
import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from app.conversation import Plan, Task
from app.schemas import ChatRequest, Classification, DialogState, Intent, Slots
from app.services import alert_policy as ap
from app.services import baseline_rationale
from app.services.conversation_memory import recall, remember
from app.workflow_tools import DataTools
from tests.test_workflow import DATA, NOW, make_engine

ROOT = Path(__file__).resolve().parents[2]


class WordsPlanner:
    """Classifies by the words the server hands it: explicit IDs -> lookup; a customer name -> ambiguous lookup."""
    client, degraded, api_style, model = None, True, 'responses', 'scripted'

    def __init__(self):
        self.seen: list[str] = []

    async def plan(self, message, state, now):
        self.seen.append(message)
        ids = re.findall(r'ORD-\d{3}', message.upper())
        if re.search(r'why\b.*\b(8|eight)\b', message, re.I):
            c = Classification(intent=Intent.OPERATIONS_NORMALITY, confidence=.9, slots=Slots(stage='ASSEMBLY'))
        elif ids:
            c = Classification(intent=Intent.ORDER_LOOKUP, confidence=.95, slots=Slots(order_ids=ids))
        elif 'trendcart' in message.lower():
            c = Classification(intent=Intent.ORDER_LOOKUP, confidence=.95, slots=Slots(customer='TrendCart'))
        else:
            c = Classification(intent=Intent.ORDER_LOOKUP, confidence=.95, slots=Slots(reference='active'))
        return Plan(tasks=[Task(message=message, classification=c)])

    async def narrate(self, message, state, responses, emit=None):
        return '\n\n'.join(r.answer for r in responses)


def talk(engine, planner, messages, emit=None):
    state, out = DialogState(), []
    engine.store.save(state)
    for m in messages:
        r = asyncio.run(engine.chat(ChatRequest(message=m, session_id=state.session_id), planner, emit=emit))
        out.append(r)
    return out


# ---------------------------------------------------------------- 2. several orders in one chat
def test_one_chat_keeps_several_orders_and_resolves_references(tmp_path: Path):
    engine, planner = make_engine(tmp_path), WordsPlanner()
    r = talk(engine, planner, ['How is ORD-005 doing?', 'What about ORD-120?', 'Go back to the first one', 'Is the other one late?', 'Compare both of them'])
    assert r[1].state.discussed_orders == ['ORD-005', 'ORD-120']
    assert planner.seen[2] == 'Go back to ORD-005' and r[2].selected_order_id == 'ORD-005'
    assert r[2].answer.startswith('(Reading “the first one” = ORD-005') and r[2].tool_calls[0].name == 'recall_conversation'
    assert planner.seen[3] == 'Is ORD-120 late?' and r[3].selected_order_id == 'ORD-120'
    assert 'ORD-005' in planner.seen[4] and 'ORD-120' in planner.seen[4]
    # the history keeps the manager's own words, not the rewrite
    assert r[4].state.history[-2]['content'] == 'Compare both of them'


def test_an_ordinal_after_a_candidate_list_picks_from_that_list(tmp_path: Path):
    engine, planner = make_engine(tmp_path), WordsPlanner()
    r = talk(engine, planner, ['How is the TrendCart order doing?', 'The second one.'])
    listed = r[0].state.pending_clarification.candidates
    assert len(listed) == 6 and r[0].state.discussed_orders == [], 'a candidate list is not a discussed order'
    assert r[1].selected_order_id == listed[1] and planner.seen[1] == listed[1] + '.'


def test_a_description_is_rewritten_only_when_one_discussed_order_matches():
    tools = DataTools(DATA)
    state = DialogState()
    remember(state, ['ORD-005', 'ORD-120'])                     # a scarf (TrendCart) and a vest (TrendCart)
    assert recall('Chase the scarf one', state, tools)[0] == 'Chase ORD-005'
    assert recall('Chase the TrendCart one', state, tools)[1] == [], 'both are TrendCart: ask, do not guess'
    state2 = DialogState()
    remember(state2, ['ORD-005', 'ORD-108'])                    # two scarf orders
    assert recall('Is the scarf one late?', state2, tools)[1] == []
    assert recall('Is the Harbor Knits one late?', state2, tools)[0] == 'Is ORD-108 late?'
    assert recall('What about ORD-007?', state2, tools)[1] == [], 'an explicit ID is never rewritten'
    assert recall('Is the other one late?', DialogState(), tools)[1] == [], 'nothing discussed yet: nothing to recall'


# ---------------------------------------------------------------- 3. tool calls shown while answering
def test_the_stream_shows_planner_tool_calls_and_narration_in_order(tmp_path: Path):
    engine, planner, events = make_engine(tmp_path), WordsPlanner(), []

    async def emit(text, kind='delta', **detail):
        events.append({'kind': kind, 'text': text, **detail})
    r = talk(engine, planner, ['How is ORD-005 doing?'], emit)[0]
    steps = [e for e in events if e['kind'] == 'step']
    assert [s['phase'] for s in steps] == ['plan', 'plan'] + ['tool'] * len(r.tool_calls) + ['narrate']
    assert steps[1]['text'] == 'order.lookup' and steps[1]['slots'] == {'order_ids': 'ORD-005'}
    assert [s['text'] for s in steps if s['phase'] == 'tool'] == [c.name for c in r.tool_calls]
    last_tool = [s for s in steps if s['phase'] == 'tool'][-1]
    assert last_tool['summary'].startswith('ORD-005: knitting') and last_tool['rows'] >= 1 and last_tool['ms'] is not None
    assert events.index(steps[-1]) < len(events), 'narration step comes before the answer text'


def test_an_emitter_that_only_takes_text_still_works(tmp_path: Path):
    engine, texts = make_engine(tmp_path), []

    async def emit(text):          # older callers: no kind, no detail
        texts.append(text)
    r = talk(engine, WordsPlanner(), ['How is ORD-005 doing?'], emit)[0]
    assert r.selected_order_id == 'ORD-005'


# ---------------------------------------------------------------- 4. why eight same weekdays
def test_why_eight_gets_the_measured_reasons(tmp_path: Path):
    r = talk(make_engine(tmp_path), WordsPlanner(), ['Why do you use 8 weeks for the baseline?'])[0]
    assert r.tool_calls[0].name == 'explain_baseline_choice' and not r.needs_clarification
    assert 'closed on Sundays' in r.answer and '0.67' in r.answer and '0.1' in r.answer
    for q in ('why not the last 7 days?', 'Why same weekday?', 'How did you choose the baseline?', 'Why eight?', 'why 8'):
        assert baseline_rationale.asks_why(q), q
    for q in ('What baseline did you use?', 'Why is ORD-005 late?', 'why 8 orders overdue', 'why not four of them?'):
        assert not baseline_rationale.asks_why(q), q


def test_the_rationale_figures_match_the_study():
    study = json.loads((ROOT / 'analysis/results/baseline_window.json').read_text())
    for k, row in baseline_rationale.STUDY.items():
        assert row['false_alerts'] == study['false_alerts'][str(k)]['p1_alerts_per_month']
        assert row['below_range_days'] == study['false_alerts'][str(k)]['watch_days_per_month']
        assert row['small_drops_caught'] == study['detection']['0.2'][str(k)]['caught_pct']
        assert row['full_baseline_days'] == study['real_log']['by_window'][str(k)]['full_baseline_stage_days']


# ---------------------------------------------------------------- 1a. automatic alert on an excursion
def snapshot():
    data, _ = DataTools(DATA).queue_snapshot(NOW)
    return data


def test_a_sudden_excursion_emails_the_same_day_and_shares_the_stage_key():
    data = snapshot()
    assert not any(a.kind == 'stage_excursion' for a in ap.detect(data, NOW)), 'the seed data has no excursion'
    for r in data['production_log']:
        if r['stage'] == 'KNITTING' and r['date'] == '2026-03-31':
            r['pieces_completed'] = '300'                        # a machine stops: about a third of a normal day
    alerts = {a.key: a for a in ap.detect(data, NOW)}
    knit = alerts['stage_drop:KNITTING']
    assert knit.kind == 'stage_excursion' and knit.tier == ap.P1 and knit.evidence[0]['output'] == 300
    assert not any(a.kind == 'low_day' and a.entity == 'KNITTING' for a in alerts.values())
    first = {d.alert.key: d.channel for d in ap.gate(list(alerts.values()), [], NOW)}
    assert first['stage_drop:KNITTING'] == 'email_now'
    # the next day the same stage problem is not emailed again (same key, cooldown); it is reminded in the digest
    history = [{'key': 'stage_drop:KNITTING', 'tier': ap.P1, 'score': knit.score, 'sent_at': NOW.isoformat(), 'channel': 'email_now'}]
    later = {d.alert.key: d.channel for d in ap.gate(list(alerts.values()), history, NOW + timedelta(hours=26))}
    assert later['stage_drop:KNITTING'] == 'digest'


def test_a_normal_low_day_is_not_an_excursion():
    data = snapshot()
    for r in data['production_log']:
        if r['stage'] == 'KNITTING' and r['date'] == '2026-03-31':
            r['pieces_completed'] = '780'                        # below the usual range, but not far outside it
    assert not any(a.kind == 'stage_excursion' for a in ap.detect(data, NOW))


def test_alert_emails_follow_the_flag_or_the_managers_switch(tmp_path: Path):
    from app.services.alert_delivery import AlertDelivery
    settings = SimpleNamespace(alert_emails_enabled=False, workflow_db=tmp_path / 'wf.sqlite3', outlook_db=tmp_path / 'o.sqlite3')
    delivery = AlertDelivery.__new__(AlertDelivery)
    delivery.settings = settings
    assert delivery.enabled({'alert_emails_enabled': False}) is False
    assert delivery.enabled({'alert_emails_enabled': True}) is True
    settings.alert_emails_enabled = True
    assert delivery.enabled({}) is True


# ---------------------------------------------------------------- 1b. voice input
def test_spoken_order_numbers_are_normalized():
    from app.api.voice_api import normalize_spoken
    assert normalize_spoken('How is O R D zero zero five doing') == 'How is ORD-005 doing'
    assert normalize_spoken('what about ord 120') == 'what about ORD-120'
    assert normalize_spoken('order number 7') == 'ORD-007'
    assert normalize_spoken('can we take order 500 hoodies') == 'can we take order 500 hoodies', 'a bare quantity is left alone'


def test_transcribe_endpoint_uses_the_speech_model_and_never_stores_audio():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import voice_api
    seen = {}

    class Transcriptions:
        async def create(self, model, file, prompt):
            seen.update(model=model, name=file[0], size=len(file[1]), prompt=prompt)
            return SimpleNamespace(text='how is o r d zero zero five doing')
    app = FastAPI()
    app.include_router(voice_api.router)
    app.state.client = SimpleNamespace(audio=SimpleNamespace(transcriptions=Transcriptions()))
    app.state.settings = SimpleNamespace(transcribe_model='whisper-1')
    app.state.workflow = SimpleNamespace(tools=DataTools(DATA))
    client = TestClient(app)
    r = client.post('/api/v1/voice/transcribe', content=b'\x1aE\xdf\xa3fake-webm', headers={'Content-Type': 'audio/webm'})
    assert r.status_code == 200 and r.json()['normalized'] == 'how is ORD-005 doing'
    assert seen['model'] == 'whisper-1' and seen['name'] == 'question.webm' and 'TrendCart' in seen['prompt']
    assert client.post('/api/v1/voice/transcribe', content=b'x', headers={'Content-Type': 'text/plain'}).status_code == 415
    app.state.client = None
    assert client.post('/api/v1/voice/transcribe', content=b'x', headers={'Content-Type': 'audio/webm'}).status_code == 503
