"""The live chat's tools and the edges between them (docs/tool_boundaries.md, docs/tool_spec.md).

Two tools were added to the live path because the brief's first two example questions had no tool there:
  get_briefing      "Did anything go wrong yesterday?"  reads the saved 07:00 briefing (discovery)
  explain_no_data   "What's our revenue?"              says what the data does not hold (refusal, wording chosen by plain code)

The classifier here is a stand-in that returns the intent a test asks for. These tests show the routing, the wording and the
safety of the server-side code. They do NOT measure how often a real model picks these intents: that needs a live run
(see docs/tool_boundaries.md, "What is not measured").
"""
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.intent_classifier import SYSTEM_PROMPT
from app.schemas import ChatRequest, Classification, Intent, Slots
from app.services.snapshot_service import DatabaseDataTools, snapshot
from app.workflow_engine import WorkflowEngine
from app.workflow_store import WorkflowStore
from app.workflow_tools import DataTools, explain_no_data

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
NOW = datetime.fromisoformat('2026-04-01T09:00:00+08:00')


class Fixed:
    def __init__(self, intent: str, confidence: float = .99, **slots: Any) -> None:
        self.result = Classification(intent=Intent(intent), slots=Slots(**slots), confidence=confidence)

    async def classify(self, message, state, now):
        return self.result


class Recorder:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, payload, idempotency_key):
        self.sent.append(payload)
        return 'test-receipt'


def csv_engine(tmp_path: Path) -> WorkflowEngine:
    return WorkflowEngine(DataTools(DATA), WorkflowStore(tmp_path / 'wf.sqlite3'), lambda: NOW, Recorder())


def run(coro):
    return asyncio.run(coro)


def names(response) -> list[str]:
    return [c.name for c in response.tool_calls]


# ---------------------------------------------------------------- get_briefing (discovery)
def saved_briefing_engine(tmp_path: Path, database) -> tuple[WorkflowEngine, dict]:
    from app.briefing_email import metadata as email_metadata
    from app.dashboard_store import metadata
    from app.forecast_store import metadata as prediction_metadata, import_forecasts
    from app.services.dashboard_service import DashboardService, forecast_asset
    email_metadata.create_all(database.engine)
    metadata.create_all(database.engine)
    prediction_metadata.create_all(database.engine)
    import_forecasts(database, forecast_asset())
    data = snapshot(database, '2026-04-01')
    assert DashboardService(database).generate_due(data, datetime.fromisoformat('2026-10-10T07:00:00+08:00'))['status'] == 'completed'
    engine = WorkflowEngine(DatabaseDataTools(database), WorkflowStore(tmp_path / 'wf.sqlite3'), lambda: NOW, Recorder())
    return engine, DatabaseDataTools(database).briefing()


def test_briefing_answers_from_the_saved_briefing_with_the_rows_behind_it(tmp_path, business_database):
    engine, saved = saved_briefing_engine(tmp_path, business_database)
    response = run(engine.chat(ChatRequest(message='Did anything go wrong yesterday?'), Fixed('briefing.today')))
    assert names(response)[0] == 'get_briefing'
    for line in (saved['yesterday'], saved['top_issue'], saved['decide']):
        assert line in response.answer, 'every line comes from the stored briefing, not from the model'
    # tracing: the production rows for the day before the briefing's business date are attached
    assert response.evidence and {e.source for e in response.evidence} >= {'production_log'}
    assert all(e.record['date'] == '2026-03-31' for e in response.evidence if e.source == 'production_log')
    assert not response.confirmation_required, 'reading a briefing never opens an action'


def test_a_follow_up_about_the_top_issue_has_an_order_to_talk_about(tmp_path, business_database):
    engine, saved = saved_briefing_engine(tmp_path, business_database)
    match = re.search(r'\bORD-\d{3}\b', saved['top_issue'])
    assert match, 'the shipped data has a flagged order'
    first = run(engine.chat(ChatRequest(message='Did anything go wrong yesterday?'), Fixed('briefing.today')))
    assert first.state.active_order == match[0]
    second = run(engine.chat(ChatRequest(message='Why is that flagged?', session_id=first.state.session_id), Fixed('order.risk', reference='active')))
    assert 'assess_order_risk' in names(second) and match[0] in second.answer


def test_no_saved_briefing_is_said_plainly(tmp_path):
    response = run(csv_engine(tmp_path).chat(ChatRequest(message='What happened yesterday?'), Fixed('briefing.today')))
    assert 'No morning briefing has been saved yet' in response.answer
    assert response.tool_calls[0].name == 'get_briefing' and response.tool_calls[0].result == {'status': 'none_saved'}
    assert 'Yesterday:' not in response.answer, 'nothing is invented when there is no briefing'


def test_a_low_confidence_briefing_guess_asks_instead_of_answering(tmp_path):
    response = run(csv_engine(tmp_path).chat(ChatRequest(message='hmm'), Fixed('briefing.today', confidence=.3)))
    assert response.needs_clarification and not response.tool_calls


# ---------------------------------------------------------------- explain_no_data (refusal)
@pytest.mark.parametrize('message,topic,must_say', [
    ("What's our revenue this month?", 'price', 'no prices, revenue or profit'),
    ('How much profit did ORD-005 make?', 'price', 'no prices, revenue or profit'),
    ('Who is the best machine operator?', 'people', 'No worker names or staffing data'),
    ('What will demand be next quarter?', 'demand', 'no demand forecast'),
    ('Delete ORD-005', 'modify', "can't cancel, delete or change orders"),
    ('Move the due date of ORD-005 to Friday', 'modify', "can't cancel, delete or change orders"),
    ('What is the weather like at the Harbor Knits site?', 'other', 'will not guess'),
])
def test_questions_the_data_cannot_answer_are_refused_in_words_chosen_by_code(tmp_path, message, topic, must_say):
    engine = csv_engine(tmp_path)
    before = (DATA / 'orders.csv').read_bytes()
    response = run(engine.chat(ChatRequest(message=message), Fixed('data.unavailable')))
    assert names(response) == ['explain_no_data'] and response.tool_calls[0].arguments == {'topic': topic}
    assert must_say in response.answer
    assert not response.confirmation_required and response.state.pending_action is None
    assert not response.needs_clarification, 'a refusal is an answer, not a question'
    assert (DATA / 'orders.csv').read_bytes() == before and not engine.sender.sent
    assert not re.search(r'\$|\d+\.\d\d', response.answer.split('\nAs of')[0]), 'no figure in a refusal'


def test_refusal_wording_does_not_depend_on_the_model():
    # same message, any slots the model might have invented: the reason is a function of the user's own words
    assert explain_no_data("What's the margin on hoodies?")['topic'] == 'price'
    assert explain_no_data('cancel the TrendCart order')['topic'] == 'modify'


# ---------------------------------------------------------------- the edges between intents
def test_every_intent_is_described_to_the_classifier():
    for intent in Intent:
        if intent != Intent.UNKNOWN:
            assert intent.value in SYSTEM_PROMPT, f'{intent.value} is missing from the classifier taxonomy'
    assert 'stays order.prioritize' in SYSTEM_PROMPT, 'the line between the briefing and a ranked order list is stated'


def test_the_tool_spec_lists_exactly_the_tools_the_engine_emits(tmp_path, business_database):
    """docs/tool_spec.md (section B) is checked against what the engine really calls, in both directions."""
    spec = (ROOT / 'docs' / 'tool_spec.md').read_text(encoding='utf-8')
    in_spec = {m[1] for m in re.findall(r'^\| (B\d+) \| `([a-z_]+)`', spec, re.M)}
    engine, _ = saved_briefing_engine(tmp_path, business_database)
    seen: set[str] = set()

    def say(message: str, intent: str, session: str | None = None, **slots: Any) -> str:
        response = run(engine.chat(ChatRequest(message=message, session_id=session), Fixed(intent, **slots)))
        seen.update(names(response))
        return response.state.session_id

    s = say('TrendCart order', 'order.lookup', customer='TrendCart')
    s = say('ORD-005', 'order.lookup', s, order_ids=['ORD-005'])
    say('Is it at risk?', 'order.risk', s, reference='active')
    say('Compare ORD-005 and ORD-021 by due date', 'order.compare', None, order_ids=['ORD-005', 'ORD-021'], comparison_fields=['due_date'])
    say('Which of ORD-005 and ORD-021 should I chase first?', 'order.compare', None, order_ids=['ORD-005', 'ORD-021'], comparison_fields=['due_date'], action='rank', criterion='due_date')
    say('What needs attention in 7 days?', 'order.prioritize', None, window_days=7)
    say('800 hoodies by the 25th delivered to the customer', 'order.commitment', None, quantity=800, product='hoodies', due_date='2026-04-25', delivery_point='customer')
    say('Is packing normal today?', 'operations.normality', None, stage='PACKING', target_date='today', baseline='same_weekday', observed_output=600)
    say('Why was packing low yesterday?', 'operations.deviation', None, stage='PACKING', target_date='yesterday')
    s = say('Chase ORD-005', 'execution.chase', None, order_ids=['ORD-005'], recipient='Planner', action='draft')
    s = say('Send it', 'execution.chase', s, order_ids=['ORD-005'], action='send')
    say('confirm', 'execution.chase', s)
    s = say('Note on ORD-005: waiting for trims', 'execution.note', None, order_ids=['ORD-005'], text='waiting for trims')
    say('confirm', 'execution.note', s)
    s = say('Remind me tomorrow at 9 a.m. if no reply for ORD-005', 'execution.reminder', None, order_ids=['ORD-005'], condition='no_reply', deadline='tomorrow 9 a.m.')
    say('confirm', 'execution.reminder', s)
    say('Did anything go wrong yesterday?', 'briefing.today')
    say("What's our revenue?", 'data.unavailable')
    say('Anything unusual?', 'discovery.findings')

    endpoints = {'ask_database', 'evidence'}          # B14 is the SQL-agent endpoint and B15 is GET /api/v1/evidence: neither is a chat ToolCall
    assert seen == in_spec - endpoints, (f'spec-only: {sorted(in_spec - endpoints - seen)}; engine-only: {sorted(seen - in_spec)}. '
                                         'Rename the tool in docs/tool_spec.md or in the engine so they agree.')
