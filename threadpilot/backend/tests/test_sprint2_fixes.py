"""Sprint 2 regression tests for the failure causes found in the 24 Oct live evaluation (evaluation/FAILURE_ANALYSIS.md).

Each test names its cause (A-F) and the eval question it protects. They use annotated classifications, so they test
the deterministic server, not the language model.
"""
import asyncio
from datetime import date
from pathlib import Path

import pytest

from app.conversation import Plan, Task
from app.prediction.aft import LeadTimeModel
from app.schemas import ChatRequest, Classification, DialogState, Intent, Slots
from app.workflow_tools import resolve_date
from tests.test_workflow import NOW, FixedClassifier, make_engine


def chat(engine, classifier, message, state=None, confirmation_id=None):
    state = state or DialogState()
    engine.store.save(state)
    return asyncio.run(engine.chat(ChatRequest(message=message, session_id=state.session_id, confirmation_id=confirmation_id), classifier))


class ScriptedPlanner:
    """Planner stand-in: a list of (intent, slots) per turn; narration joins the server answers."""
    client, degraded, api_style = None, True, 'responses'

    def __init__(self, *turns):
        self.turns, self.i = list(turns), 0

    async def plan(self, message, state, now):
        intent, slots = self.turns[self.i]
        self.i += 1
        return Plan(tasks=[Task(message=message, classification=Classification(intent=Intent(intent), confidence=.95, slots=Slots(**slots)))])

    async def narrate(self, message, state, responses, emit=None):
        return '\n\n'.join(r.answer for r in responses)

    async def compose_chase(self, request, revision, facts, order_ids, previous, fallback, emit=None, **kwargs):
        return fallback


# ---------------------------------------------------------------- cause A: redundant clarification
def test_normality_asks_only_for_the_missing_stage_and_defaults_the_baseline(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, FixedClassifier('operations.normality', stage='ASSEMBLY', target_date='yesterday'), "Was yesterday's assembly output normal?")
    assert not r.needs_clarification and r.tool_calls[0].name == 'check_normality'
    data = r.tool_calls[0].result
    assert (data['output'], data['status'], data['minimum'], data['maximum']) == (455, 'below', 687, 807)
    assert 'baseline_note' in data and data['baseline_records'][-1]['date'] == '2026-03-24'
    r = chat(engine, FixedClassifier('operations.normality', observed_output=800), 'Is 800 pieces normal?')
    assert r.needs_clarification and 'Which stage' in r.answer


def test_production_output_is_a_plain_lookup(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.output', stage='KNITTING', target_date='2026-03-28'), 'What was knitting output on 28 March 2026?')
    assert r.tool_calls[0].name == 'get_production_output' and '1031' in r.answer and not r.needs_clarification
    r = chat(make_engine(tmp_path), FixedClassifier('operations.output', target_date='2026-03-29'), 'Output on 29 March?')
    assert 'Sunday' in r.answer


def test_weekday_names_resolve_against_the_business_clock():
    assert resolve_date('this Saturday', NOW) == date(2026, 4, 4)
    assert resolve_date('Saturday', NOW) == date(2026, 4, 4)
    assert resolve_date('next Monday', NOW) == date(2026, 4, 13)
    assert resolve_date('the 25th', NOW) == date(2026, 4, 25)


# ---------------------------------------------------------------- cause B: narrowing after a candidate list
def test_the_scarf_order_narrows_without_planner_slots(tmp_path: Path):
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('order.lookup', {'customer': 'TrendCart'}), ('order.lookup', {}), ('order.risk', {'reference': 'active'}))
    state = DialogState()
    engine.store.save(state)
    r1 = asyncio.run(engine.chat(ChatRequest(message='How is the TrendCart order doing?', session_id=state.session_id), planner))
    assert r1.needs_clarification and len(r1.order_ids) == 6
    r2 = asyncio.run(engine.chat(ChatRequest(message='The scarf order.', session_id=state.session_id), planner))
    assert r2.selected_order_id == 'ORD-005' and not r2.needs_clarification
    r3 = asyncio.run(engine.chat(ChatRequest(message='Is it already late?', session_id=state.session_id), planner))
    assert 'Not past due' in r3.answer and r3.selected_order_id == 'ORD-005'


# ---------------------------------------------------------------- cause C: tools that did not exist
def test_rank_by_idle_days_and_list_workshops(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.rank', criterion='idle_days', window_days=3), 'Which order has gone the longest without activity?')
    assert r.tool_calls[0].result['orders'][0]['order_id'] == 'ORD-002' and r.tool_calls[0].result['orders'][0]['idle_days'] == 9
    r = chat(make_engine(tmp_path), FixedClassifier('data.workshops', product='accessories'), 'Which workshops can make accessories?')
    data = r.tool_calls[0].result
    assert {w['workshop_id'] for w in data['eligible']} == {'W2', 'W4', 'W6'}
    assert any(w['workshop_id'] == 'W7' and 'SUSPENDED' in w['excluded_because'][0] for w in data['excluded'])
    r = chat(make_engine(tmp_path), FixedClassifier('data.workshops', product='tops', quantity=250), '250 tops?')
    assert {w['workshop_id'] for w in r.tool_calls[0].result['eligible']} == {'W1', 'W2', 'W3', 'W5', 'W6', 'W8'}


def test_summary_carries_overdue_idle_and_on_time_aggregates(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = asyncio.run(engine.chat(ChatRequest(message='How many orders are overdue?'), ScriptedPlanner(('order.summary', {}))))
    data = r.tool_calls[0].result
    assert data['overdue_active']['count'] == 8 and data['completed_delivery'] == {**data['completed_delivery'], 'completed': 86, 'late': 34, 'on_time_rate_pct': 60.5}
    assert data['idle_days_active']['top'][0] == {'order_id': 'ORD-002', 'idle_days': 9}
    r = asyncio.run(engine.chat(ChatRequest(message='Orders for Zara?'), ScriptedPlanner(('order.summary', {'customer': 'Zara'}))))
    assert 'No orders recorded for customer' in r.answer


# ---------------------------------------------------------------- cause D: refusals before clarification
@pytest.mark.parametrize('message, reason', [
    ('What revenue did the TrendCart orders bring in?', 'money'),
    ('Delete ORD-120 from the system.', 'delete'),
    ('Cancel order ORD-017 and tell the customer.', 'cancel'),
    ('Which worker was responsible for the assembly slowdown?', 'people'),
])
def test_unknown_requests_for_non_goals_are_refused_not_questioned(tmp_path: Path, message, reason):
    r = chat(make_engine(tmp_path), FixedClassifier('unknown'), message)
    assert r.intent == Intent.UNANSWERABLE and not r.needs_clarification and not r.confirmation_required
    assert r.tool_calls[0].name == 'explain_no_data' and r.tool_calls[0].result['reason'] == reason
    assert 'Which order' not in r.answer


# ---------------------------------------------------------------- cause E: unknown order is an answer
def test_unknown_order_id_is_answered_not_raised(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.refresh', order_ids=['ORD-999']), 'What stage is ORD-999 in?')
    assert 'no order ORD-999' in r.answer and r.tool_calls[0].result['status'] == 'not_found' and r.selected_order_id is None


# ---------------------------------------------------------------- feasibility v2 and the AFT model
def test_capacity_leads_with_queue_projection_and_aft_band(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.commitment', quantity=800, product='hoodies', due_date='2026-04-25', delivery_point='customer'), '800 hoodies by 25 April, delivered?')
    data = r.tool_calls[0].result
    assert data['queue_projection']['verdict'] in ('likely', 'tight', 'unlikely') and data['queue_projection']['best_case']['finish_date']
    assert 0 <= data['historical_lead_time_model']['p_on_time'] <= 1
    assert data['worst_case_serial_backlog']['scenario_required_days'] == 141 and data['available_workdays'] == 21
    assert data['preliminary'] != 'not supported by conservative estimate'


def test_aft_port_matches_the_prediction_notes():
    model = LeadTimeModel()
    assert round(model.typical_lead_days(705.23), 1) == 23.6
    f = model.forecast_order({'order_id': 'ORD-005', 'pieces': '500', 'order_date': '2026-03-21', 'due_date': '2026-04-20'}, date(2026, 4, 1))
    assert (f['delay_probability'], f['risk_level'], f['expected_completion_date']) == (0.059, 'LOW', '2026-04-11')
    assert f['completion_range_80pct'] == ['2026-04-06', '2026-04-19']


def test_order_forecast_route(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.forecast', order_ids=['ORD-005']), 'How likely is ORD-005 to be late?')
    assert r.tool_calls[-1].name == 'predict_order_delay' and 'delay probability 6%' in r.answer
    r = chat(make_engine(tmp_path), FixedClassifier('order.forecast', order_ids=['ORD-057']), 'ORD-057?')
    assert 'this one is complete' in r.answer


# ---------------------------------------------------------------- confirmations keep naming the order
def test_reminder_confirmation_names_the_order(tmp_path: Path):
    engine = make_engine(tmp_path)
    state = DialogState()
    r = chat(engine, FixedClassifier('execution.reminder', order_ids=['ORD-002'], condition='no_activity', deadline='tomorrow 2 pm'), 'Remind me tomorrow at 2 pm if ORD-002 has not moved', state)
    assert r.confirmation_required and '2026-04-02T14:00:00+08:00' in r.answer
    r = chat(engine, FixedClassifier('execution.reminder'), 'Confirm.', r.state, r.confirmation_id)
    assert r.tool_calls[-1].name == 'upsert_reminder' and 'ORD-002' in r.answer and 'no activity' in r.answer


# ---------------------------------------------------------------- 26 Oct: discovery, stage watches, manager key
def test_find_anomalies_ranks_the_planted_assembly_drop_first(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.discovery'), 'Did anything go wrong yesterday?')
    data = r.tool_calls[0].result
    assert r.tool_calls[0].name == 'find_anomalies' and data['findings'][0]['key'] == 'stage_drop:ASSEMBLY'
    assert data['total'] >= 10 and 'Assembly has been below its normal range' in r.answer
    r = chat(make_engine(tmp_path), FixedClassifier('operations.discovery', customer='TrendCart', window_days=3), 'Anything unusual with TrendCart?')
    assert all('TrendCart' in f['title'] for f in r.tool_calls[0].result['findings'])


def test_stage_watch_is_previewed_confirmed_and_evaluated(tmp_path: Path):
    from datetime import timedelta
    engine = make_engine(tmp_path)
    state = DialogState()
    r = chat(engine, FixedClassifier('execution.reminder', stage='PACKING', deadline='tomorrow'), 'Remind me tomorrow if packing is still behind.', state)
    assert r.confirmation_required and 'watch on packing' in r.answer and '2026-04-02T07:00:00+08:00' in r.answer
    r = chat(engine, FixedClassifier('execution.reminder'), 'Confirm.', r.state, r.confirmation_id)
    assert r.tool_calls[-1].name == 'upsert_reminder' and 'Watch created on packing' in r.answer
    engine.store.evaluate_reminders(NOW + timedelta(days=1), engine.tools)
    notes = engine.store.notifications(state.session_id)
    assert len(notes) == 1 and 'No production record for PACKING on 2026-04-01' in notes[0]['message']


def test_planner_key_cannot_confirm_but_manager_key_can(tmp_path: Path):
    engine = make_engine(tmp_path)
    state = DialogState()
    r = chat(engine, FixedClassifier('execution.note', order_ids=['ORD-002'], text='escalated today'), 'Add a note to ORD-002: escalated today', state)
    assert r.confirmation_required
    denied = asyncio.run(engine.chat(ChatRequest(message='Save it.', session_id=state.session_id, confirmation_id=r.confirmation_id), FixedClassifier('execution.note'), role='planner'))
    assert 'manager key is required' in denied.answer and not denied.tool_calls and denied.state.pending_action is not None
    saved = asyncio.run(engine.chat(ChatRequest(message='Save it.', session_id=state.session_id, confirmation_id=r.confirmation_id), FixedClassifier('execution.note'), role='manager'))
    assert saved.tool_calls[-1].name == 'save_internal_note'


def test_resolve_role_with_and_without_a_manager_key():
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app.api.security import resolve_role
    both = SimpleNamespace(api_access_token=SecretStr('ws'), manager_access_token=SecretStr('mg'))
    assert (resolve_role('ws', both), resolve_role('mg', both), resolve_role('x', both)) == ('planner', 'manager', None)
    single = SimpleNamespace(api_access_token=SecretStr('ws'), manager_access_token=SecretStr(''))
    assert (resolve_role('ws', single), resolve_role('x', single)) == ('manager', None)
