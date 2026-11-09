"""Grounding: an order, product, stage, customer or workshop that is not in the records is answered with what is on file,
never guessed, never a stale candidate list, never a crash. Rows refer to the 'Similar Questions' tab of the 100-question
sheet (a different factory's vocabulary: jackets, embroidery, W9, Cedar Apparel, ORD-218…); the offline run lives in
evaluation/q100/ (Q100_SET=similar)."""
from pathlib import Path

from tests.test_sprint2_fixes import ScriptedPlanner, chat
from tests.test_workflow import make_engine

NO_ORDER = 'There is no order ORD-218 in the current records'


def test_unknown_order_numbers_in_every_spelling(tmp_path: Path):
    engine = make_engine(tmp_path)
    for text, spec in [('What is the status of order 218?', ('order.lookup', {})), ('Show me the status of 237.', ('order.lookup', {'reference': 'ambiguous'})),
                       ('Show status of order two one eight.', ('order.lookup', {})), ('Expedite order 244.', ('order.expedite', {})),
                       ('Refresh ORD-244.', ('order.refresh', {'order_ids': ['ORD-244'], 'reference': 'explicit'}))]:
        r = chat(engine, ScriptedPlanner(spec), text)
        assert 'in the current records' in r.answer and 'ORD-001 to ORD-120' in r.answer and not r.needs_clarification, text
        assert r.state.active_order is None


def test_unknown_orders_do_not_crash_compare_or_chase(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('order.compare', {'order_ids': ['ORD-244', 'ORD-286'], 'reference': 'explicit'})), 'Compare ORD-244 and ORD-286 on remaining workload.')
    assert r.answer.startswith('None of ORD-244, ORD-286 is in the current records') and 'nothing was compared' in r.answer
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'send', 'order_ids': ['ORD-256'], 'reference': 'explicit', 'recipient': 'W7'})), 'Just send the chase for ORD-256 to W7. Skip the preview.')
    assert 'There is no order ORD-256' in r.answer and 'Nothing was drafted, saved or scheduled' in r.answer and not any(c.name == 'send_chase' and c.executed for c in r.tool_calls)
    r = chat(engine, ScriptedPlanner(('order.compare', {'reference': 'ambiguous'})), '244 vs 286: tougher production pace?')
    assert 'None of ORD-244, ORD-286' in r.answer


def test_unknown_order_is_not_carried_into_the_next_turn(tmp_path: Path):
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('execution.reminder', {'action': 'create', 'order_ids': ['ORD-256'], 'reference': 'explicit', 'condition': 'no_activity', 'deadline': 'next Tuesday'}),
                              ('execution.reminder', {'action': 'create', 'reference': 'active', 'condition': 'no_reply', 'deadline': '2026-04-02T16:00'}))
    r = chat(engine, planner, 'Remind me if ORD-256 has not moved by next Tuesday.')
    r = chat(engine, planner, 'Remind me if there is no reply by tomorrow at 4 p.m.', r.state)
    assert r.needs_clarification and 'ORD-256' not in r.answer and not r.confirmation_required


def test_unknown_product_and_order_type(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('order.risk_overview', {'product': 'jackets'})), 'Are the jacket orders moving?')
    assert r.answer.startswith('No jacket orders in the records') and 'Beanie, Cardigan, Crewneck sweater, Hoodie, Polo shirt, Scarf, Vest' in r.answer
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'product': 'uniform'})), 'Which uniform orders require my attention?')
    assert r.answer.startswith("The records do not tag orders as 'uniform'") and 'TrendCart' in r.answer
    r = chat(engine, ScriptedPlanner(('order.rank', {'criterion': 'idle_days', 'product': 'jackets'})), 'Which active jacket orders have gone quiet the longest?')
    assert r.answer.startswith('No jacket orders in the records')
    # real products still work
    r = chat(engine, ScriptedPlanner(('order.risk', {'reference': 'active', 'action': 'recommend', 'product': 'cardigan'})), 'Should I chase this cardigan order?')
    assert r.needs_clarification and '4 active cardigan orders' in r.answer


def test_quantity_and_product_with_no_match_is_an_answer(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.chase', {'action': 'draft', 'quantity': 900, 'product': 'vests'})), 'Chase the order with 900 vests.')
    assert r.answer.startswith('No active vest order of 900 pieces') and 'ORD-120 (1500 pieces' in r.answer and 'Draft' not in r.answer


def test_unknown_stage_names_the_four_real_ones(tmp_path: Path):
    engine = make_engine(tmp_path)
    for text, spec in [('Was sewing output on 20 May 2026 normal?', ('operations.normality', {'target_date': '2026-05-20'})),
                       ('Show the last recorded activity on the embroidery line.', ('operations.output', {})),
                       ('Expedite orders stuck at the embroidery stage.', ('order.expedite', {'reference': 'ambiguous'})),
                       ('Remind me tomorrow afternoon if embroidery output is below the normal range.', ('execution.reminder', {'action': 'create', 'condition': 'stage_below_range', 'deadline': '2026-04-02T14:00'})),
                       ('Is cutting causing the sewing drop?', ('operations.deviation', {'action': 'explain'}))]:
        r = chat(engine, ScriptedPlanner(spec), text)
        assert "stage in this factory's records: the stages are knitting → assembly → washing → packing" in r.answer, text
        assert not r.confirmation_required
    r = chat(engine, ScriptedPlanner(('operations.normality', {'target_date': '2026-05-20'})), 'Was sewing output on 20 May 2026 normal?')
    assert 'the production log ends 2026-03-31' in r.answer
    # "finishing" is ordinary English, not a foreign stage
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'criterion': 'risk'})), 'Which jobs look on schedule today but have too little remaining time for finishing and packing?')
    assert 'Ranked by delivery risk' in r.answer


def test_unknown_customer_lists_the_customers_on_file(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'draft', 'customer': 'Cedar Apparel'})), 'Chase all Cedar Apparel orders.')
    assert r.answer.startswith('No customer named Cedar Apparel in the records') and 'Northwind Apparel' in r.answer and 'Draft' not in r.answer
    r = chat(engine, ScriptedPlanner(('order.compare', {'reference': 'ambiguous', 'customer': 'Cedar Apparel'})), 'Cedar Apparel or Seabrook Textiles, whose orders look worse?')
    assert r.answer.startswith('No customer named Cedar Apparel')
    r = chat(engine, ScriptedPlanner(('order.lookup', {'customer': 'Seabrook Textiles'})), "Is there anything on Seabrook Textiles' orders I need to act on this morning?")
    assert r.answer.startswith('No customer named Seabrook Textiles')
    # a typo of a real customer is still that customer
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'draft', 'customer': 'Trend Cart'})), 'Chase the Trend Cart order.')
    assert 'No customer named' not in r.answer


def test_unknown_workshop_and_meeting_reference(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-017'], 'reference': 'explicit', 'recipient': 'W9'})), 'Ask W9 whether Monday is when they can receive the ORD-017 batch.')
    assert r.answer.startswith('W9 is not a workshop on file: the workshops are W1–W8') and 'Draft' not in r.answer
    r = chat(engine, ScriptedPlanner(('execution.note', {'action': 'save', 'reference': 'ambiguous', 'text': 'revisit next Monday'})), "Note that we will revisit the third order from yesterday's planning meeting next Monday?")
    assert r.answer.startswith('Meeting notes and conversations are not in the records') and not r.confirmation_required


def test_dates_beyond_the_records_and_future_windows(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'window_days': 7, 'due_date': '2026-06-01'})), 'Which orders are at risk of becoming late between June 1 and June 11?')
    assert r.answer.startswith('No active orders are due between 2026-06-01 and 2026-06-11') and 'latest due date among active orders is 2026-05-01' in r.answer
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'window_days': 7})), "What's due from 1 to 11 June that could slip?")
    assert '2026-06-01 and 2026-06-11' in r.answer
    r = chat(engine, ScriptedPlanner(('order.commitment', {'quantity': 700, 'product': 'jackets', 'due_date': '2026-06-03', 'delivery_point': 'factory'})), 'Can we take an order for 700 jackets due on June 3?')
    assert r.answer.startswith('700 jackets by 2026-06-03') and 'no jackets orders in the history' in r.answer and 'size-based lead-time model' in r.answer


def test_no_draft_to_revise_or_send_says_so(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'revise', 'text': 'add the merchandising manager in CC'})), 'Add the merchandising manager in CC.')
    assert r.answer.startswith('There is no draft in this chat to revise')
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'send', 'recipient': 'W7'})), 'Skip the preview and send the W7 chase.')
    assert r.answer.startswith('There is no unsent draft in this chat, so nothing was sent')
    r = chat(engine, ScriptedPlanner(('unknown', {})), 'Okay, the embroidery draft looks fine.')
    assert r.answer.startswith('Nothing is waiting for confirmation')


def test_chase_from_the_largest_customer_is_not_a_customer_email(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.chase', {'action': 'draft', 'reference': 'ambiguous'})), 'Chase all orders from the customer with the largest open order volume.')
    assert 'I do not write to customers' not in r.answer and 'most active pieces outstanding' in r.answer and 'Northwind Apparel' in r.answer
