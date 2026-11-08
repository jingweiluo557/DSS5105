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
    assert norm('remind me fri if 017 still stuck') == 'remind me Friday if 017 still stuck'


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
    assert not r.needs_clarification and 'stage WASHING' in r.answer
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
