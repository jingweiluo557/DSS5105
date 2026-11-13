"""Regression tests for the 100-question × 3-context sheet (DSS5105_Questions, "100Q 3 Context Same Structure").
Each test names the sheet row it protects. Annotated classifications drive the deterministic server, so these test the
routing, the tools and the wording, not the language model. The full offline run lives in evaluation/q100/.
"""
from pathlib import Path

from app.services.order_refs import expand_shorthand, normalize_order_numbers, normalize_order_refs, words_to_digits
from app.workflow_engine import stages_in
from tests.test_sprint2_fixes import ScriptedPlanner, chat
from tests.test_workflow import make_engine

KNOWN = set(range(1, 121))
PRODUCTS = {'Scarf', 'Cardigan', 'Hoodie', 'Vest', 'Beanie', 'Polo shirt', 'Crewneck sweater'}


def norm(text):
    return normalize_order_numbers(normalize_order_refs(expand_shorthand(text)), KNOWN, PRODUCTS)


# ---------------------------------------------------------------- rows 9, 28, 63, 67: the manager's spellings of an order
def test_row9_spoken_number_words_with_tens_become_the_order_id():
    assert words_to_digits('zero zero zero zero twenty nine') == '000029'
    assert norm('Chase order number zero zero zero zero twenty nine') == 'Chase ORD-029'
    assert norm('Chase order 0000029') == 'Chase ORD-029'


def test_row28_two_bare_numbers_compared_are_two_orders_but_quantities_are_not():
    assert norm('29 versus 108: tougher production pace?') == 'ORD-029 versus ORD-108: tougher production pace?'
    assert norm('Between orders 29 and 108, which needs the higher rate?') == 'Between ORD-029 and ORD-108, which needs the higher rate?'
    assert norm('600 scarves by 4/6 or 1500 cardigans by 4/10') == '600 scarves by 4/6 or 1500 cardigans by 4/10'
    assert norm('Show me status of first 20 orders') == 'Show me status of first 20 orders'


def test_rows63_67_shorthand_is_expanded_before_parsing():
    assert norm('was assembly output last wk normal?') == 'was assembly output last week normal?'
    assert norm('remind me tmrw if no reply') == 'remind me tomorrow if no reply'
    assert norm('remind me fri if 017 still stuck') == 'remind me Friday if ORD-017 still stuck'   # a zero-padded number is an order number (held-out X07)


def test_row65_one_letter_slip_in_a_stage_name_still_names_the_stage():
    assert stages_in('is knittng the reason assembly is low?') == ['ASSEMBLY', 'KNITTING']
    assert stages_in('is 800 pcs normal for assembely?') == ['ASSEMBLY']


# ---------------------------------------------------------------- rows 7, 8, 15, 16: a description names the candidates
def test_row7_chase_the_order_with_a_quantity_and_category_lists_the_matches(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.chase', {'action': 'draft', 'quantity': 1500, 'product': 'tops'})), 'Chase the order with 1500 tops')
    assert r.needs_clarification and '3 active tops orders of 1500 pieces' in r.answer and 'ORD-120' in r.answer and 'ORD-099' in r.answer
    assert r.selected_order_id is None and 'Draft' not in r.answer


def test_row8_orders_stuck_at_a_stage_are_listed_for_expedite(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.expedite', {'reference': 'ambiguous'})), 'Prioritize orders that pending process at washing phase')
    assert r.needs_clarification and '10 active orders are at washing' in r.answer and 'ORD-083' in r.answer


def test_row15_overdue_threshold_in_hours_or_days_filters_the_candidates(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.chase', {'action': 'draft', 'reference': 'ambiguous'})), 'Chase orders overdued > 2 days')
    assert r.needs_clarification and '6 active orders are more than 2 days overdue' in r.answer and 'ORD-107' in r.answer and 'ORD-055' not in r.answer


def test_row16_largest_customer_is_computed_not_guessed(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.chase', {'action': 'draft', 'reference': 'ambiguous'})), 'Chase all orders from largest customer')
    assert r.needs_clarification and 'Loom & Leaf and TrendCart each have the most active orders (6)' in r.answer


# ---------------------------------------------------------------- rows 10-13: "this order" after an earlier turn
def test_rows10_13_the_order_in_focus_survives_a_change_of_intent(tmp_path: Path):
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-029'], 'reference': 'explicit'}),
                              ('order.refresh', {'reference': 'active'}),
                              ('order.lookup', {'reference': 'active'}),
                              ('order.risk', {'reference': 'active'}))
    r = chat(engine, planner, 'Chase order 0000029')
    assert 'ORD-029' in r.answer   # no mailbox in the test engine: it asks who should receive the draft
    state = r.state
    r = chat(engine, planner, 'Has the order moved yet?', state)
    assert not r.needs_clarification and r.answer.startswith('ORD-029')
    r = chat(engine, planner, 'The order is at which stage now?', r.state)
    assert not r.needs_clarification and 'stage washing' in r.answer
    r = chat(engine, planner, 'Should i chase this order?', r.state)
    assert not r.needs_clarification and 'ORD-029' in r.answer


def test_row6_bare_number_after_another_lookup_is_read_as_that_order(tmp_path: Path):
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('order.lookup', {'order_ids': ['ORD-050'], 'reference': 'explicit'}), ('order.lookup', {'reference': 'ambiguous'}))
    r = chat(engine, planner, 'Status of order 50')
    r = chat(engine, planner, 'Show me status of 55', r.state)
    assert not r.needs_clarification and r.answer.startswith('ORD-055')


# ---------------------------------------------------------------- rows 45, 60: sizes and hypothetical figures
def test_row45_lead_time_for_a_size_is_a_forecast_not_a_candidate_list(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.forecast', {'quantity': 1000, 'product': 'Hoodie'})), 'What was the typical lead time for past orders of one thousand hoodies?')
    assert not r.needs_clarification and 'hoodie' in r.answer.lower() and 'calendar days' in r.answer


def test_row60_hypothetical_output_is_judged_for_today_even_after_a_dated_question(tmp_path: Path):
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('operations.normality', {'stage': 'ASSEMBLY', 'target_date': '2026-03-26'}),
                              ('operations.normality', {'stage': 'ASSEMBLY', 'observed_output': 800}))
    r = chat(engine, planner, 'Was assembly normal on 26 March?')
    r = chat(engine, planner, 'Is 800 pieces a normal day for assembly?', r.state)
    assert '800 pieces would be within its normal range' in r.answer and 'Wednesday' in r.answer


# ---------------------------------------------------------------- rows 93, 98: notes corrected and read back
def test_row93_correction_not_that_order_targets_the_right_order(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.note', {'action': 'update', 'order_ids': ['ORD-083', 'ORD-038'], 'text': 'pausing outsourcing'})),
             'I mistyped the order number. The note about pausing outsourcing was for ORD-083, not ORD-038. Can you correct it?')
    assert r.confirmation_required and 'Internal note for ORD-083' in r.answer and 'ORD-038' not in r.answer


def test_row98_which_order_holds_the_note_is_a_read_of_both(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.note', {'action': 'read', 'order_ids': ['ORD-002', 'ORD-020'], 'text': 'customer colour approval'})),
             'Is the note about customer colour approval on ORD-002 or ORD-020?')
    assert not r.confirmation_required and 'ORD-002: no saved note' in r.answer and 'ORD-020: no saved note' in r.answer and 'Nothing was changed' in r.answer


# ---------------------------------------------------------------- 8 Nov gap fixes: answers instead of JSON or an extra question
def test_row39_41_forecast_leads_with_a_verdict_and_two_options_are_compared(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('order.commitment', {'quantity': 600, 'product': 'scarves', 'due_date': '2026-04-06', 'delivery_point': 'factory'})), 'Can we finish 600 scarves by April 6?')
    assert r.answer.startswith('600 scarves by 2026-04-06 (ready at the factory): ') and 'working day' in r.answer and 'Conditional forecast, not a promise' in r.answer
    r = chat(engine, ScriptedPlanner(('order.commitment', {'product': 'beanies', 'due_date': '2026-04-07'})), 'Maximum beanies by 2026-04-07?')
    assert not r.needs_clarification and ('No new beanies order of any size' in r.answer or 'Up to about' in r.answer)
    assert any(c.name == 'estimate_capacity' and 'max_quantity' in c.result for c in r.tool_calls)


def test_row28_required_daily_pace_compares_two_orders(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.compare', {'order_ids': ['ORD-029', 'ORD-108'], 'reference': 'explicit'})), '29 versus 108: tougher production pace?')
    assert not r.needs_clarification and 'pieces per working day needed' in r.answer and 'needs the tougher pace' in r.answer
    assert any(c.name == 'compare_orders' and c.arguments.get('criterion') == 'required_daily_pace' for c in r.tool_calls)


def test_row29_unnamed_customers_are_all_ranked(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.compare', {})), 'Which customer has the greater share of in-progress orders without recent verified movement?')
    assert not r.needs_clarification and 'has the greater share of in-progress orders without recent recorded activity' in r.answer and 'Cotton Club' in r.answer


def test_row54_customer_level_question_is_a_summary_not_which_order(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.lookup', {'customer': 'TrendCart'})), 'Is there anything on TrendCart’s orders I need to act on today?')
    assert not r.needs_clarification and r.answer.startswith('TrendCart: 6 active orders') and 'ORD-120' in r.answer and 'overdue' in r.answer
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.lookup', {'customer': 'TrendCart'})), 'Show me the TrendCart order.')
    assert r.needs_clarification   # dialogue design row 2: a single "the order" still asks which


def test_rows48_30_27_prioritise_by_customer_stage_and_risk(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'window_days': 0})), 'Which customer needs an update first, based on their in-progress overdue orders?')
    assert r.answer.startswith('By customer') and 'Northwind Apparel: 2 overdue' in r.answer and 'first:' in r.answer
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'window_days': 7, 'stage': 'WASHING'})), 'Among orders currently in washing, which should move to packing first?')
    assert 'Only orders at washing' in r.answer and 'ORD-002' in r.answer and 'ORD-107' not in r.answer
    r = chat(engine, ScriptedPlanner(('order.prioritize', {'criterion': 'risk'})), 'Rank active orders by their risk of missing the promised dispatch date.')
    assert not r.needs_clarification and 'Ranked by delivery risk' in r.answer and 'will miss even in the best case:' in r.answer and 'ORD-029' in r.answer


def test_row3_orders_due_n_days_ago(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.prioritize', {'window_days': 0})), 'Status of orders overdued 2 days ago')
    assert 'Orders due on 2026-03-30' in r.answer and 'ORD-079' in r.answer and not r.needs_clarification


def test_row50_one_stage_focus_verdict(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('operations.discovery', {})), 'If we focus on one stage today, which stage would reduce delivery risk most?')
    assert r.answer.startswith('Focus on assembly today') and any(c.name == 'stage_focus' for c in r.tool_calls)


def test_rows19_24_trace_questions_state_what_the_record_holds(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.risk', {'order_ids': ['ORD-120'], 'reference': 'explicit', 'action': 'explain'})), 'ORD-120: upstream delay or assembly dwell?')
    assert 'no stage-entry or hand-off dates' in r.answer and 'ORD-120' in r.answer


def test_row25_idle_ranking_filtered_to_orders_due_soon(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.rank', {'criterion': 'idle_days', 'window_days': 7})), 'Near due and no fresh update: which orders?')
    assert 'Only active orders due between 2026-04-01 and 2026-04-08' in r.answer and 'ORD-108' in r.answer and 'ORD-002' not in r.answer


def test_row80_acknowledgement_with_nothing_pending(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('unknown', {})), 'ok')
    assert not r.needs_clarification and r.answer.startswith('Nothing is waiting for confirmation')


def test_row84_clock_times_resolve_in_the_factory_day():
    from datetime import datetime
    from app.workflow_tools import resolve_datetime
    now = datetime.fromisoformat('2026-04-01T12:00:00+08:00')
    assert resolve_datetime('2:30', now).hour == 14 and resolve_datetime('11:30', now).hour == 11
    assert resolve_datetime('end of today', now).hour == 18
    assert resolve_datetime('Friday morning', now) is None    # dialogue design row 46: a vague time is asked, not guessed


def test_row76_draft_and_send_in_one_breath_shows_the_preview(tmp_path: Path):
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-017'], 'reference': 'explicit'}),
                              ('execution.chase', {'action': 'send', 'order_ids': ['ORD-083'], 'reference': 'explicit', 'department': 'PACKING', 'recipient': 'packing'}))
    r = chat(engine, planner, 'Draft a chase-up for ORD-017.')
    r = chat(engine, planner, 'Draft a chase-up to the packing workshop for ORD-083 and send it.', r.state)
    assert 'Nothing is sent without a preview' in r.answer and 'ORD-083' in r.answer and not any(c.name == 'send_chase' and c.executed for c in r.tool_calls)
