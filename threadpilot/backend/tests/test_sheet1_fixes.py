"""Regression tests for the 26 Oct question sheet (DSS5105_Questions, sheet 1): the rows the team marked wrong or
partial against the 23 Oct live build. Each test names the sheet row it protects. Annotated classifications drive the
deterministic server, so these test the routing, the tools and the wording, not the language model.
"""
from datetime import date
from pathlib import Path

import pytest

from app.schemas import DialogState
from app.workflow_tools import parse_day, resolve_period
from tests.test_sprint2_fixes import ScriptedPlanner, chat
from tests.test_workflow import NOW, FixedClassifier, make_engine


# ---------------------------------------------------------------- dates and periods in the manager's words
def test_parse_day_accepts_iso_day_month_and_rejects_impossible_dates():
    assert parse_day('2026-03-31', NOW) == date(2026, 3, 31)
    assert parse_day('25 March', NOW) == date(2026, 3, 25)
    assert parse_day('March 25', NOW) == date(2026, 3, 25)
    assert parse_day('yesterday', NOW) == date(2026, 3, 31)
    with pytest.raises(ValueError):
        parse_day('2026-02-31', NOW)


@pytest.mark.parametrize('text, start, end', [
    ('since 25 March', '2026-03-25', '2026-03-31'),
    ('over the last three working days', '2026-03-28', '2026-03-31'),
    ('in late March', '2026-03-21', '2026-03-31'),
    ('from 25 March to 31 March', '2026-03-25', '2026-03-31'),
])
def test_resolve_period_from_words(text, start, end):
    period = resolve_period(text, NOW, date(2026, 3, 31))
    assert (period['start'].isoformat(), period['end'].isoformat()) == (start, end)


def test_resolve_period_ignores_single_dates():
    assert resolve_period('Was PACKING output on 2026-03-31 normal?', NOW, date(2026, 3, 31)) is None


# ---------------------------------------------------------------- rows 20-39: production questions
def test_row20_stage_and_date_given_is_answered_not_questioned(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', stage='PACKING', target_date='2026-03-31'), 'Was PACKING output on 2026-03-31 normal?')
    assert not r.needs_clarification and r.tool_calls[0].result['output'] == 657 and 'within its normal range' in r.answer


def test_row24_25_invalid_date_and_sunday_are_answers(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', stage='WASHING', target_date='2026-02-31'), 'How far was WASHING output on 2026-02-31 from its usual level?')
    assert r.needs_clarification and '2026-02-31 is not a valid date (February 2026 has 28 days)' in r.answer
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', stage='WASHING', target_date='2026-02-15'), 'How far was WASHING output on 2026-02-15 from its usual level?')
    assert not r.needs_clarification and 'Sunday' in r.answer and 'closed' in r.answer and 'insufficient' not in r.answer


def test_row26_27_all_stages_compared_and_latest_record_fallback(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', target_date='today', observed_output=0), 'Which stage is most off its usual pace today?')
    assert r.tool_calls[0].name == 'stage_comparison' and r.tool_calls[0].result['most_off'] == 'ASSEMBLY'
    assert 'No production record for 2026-04-01' in r.answer and 'Assembly is the stage to worry about on 2026-03-31' in r.answer
    assert 'reported output was 0' not in r.answer
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', target_date='2026-03-31'), 'Which stage should I worry about most in 2026-03-31?')
    assert not r.needs_clarification and all(s in r.answer for s in ('knitting 905', 'assembly 455', 'washing 732', 'packing 657'))


def test_row29_period_window_counts_days_below_band(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', stage='ASSEMBLY'), 'Has ASSEMBLY been consistently below its usual level over the last three working days?')
    assert r.tool_calls[0].name == 'production_window'
    summary = r.tool_calls[0].result['summary'][0]
    assert (summary['working_days'], summary['days_below_band'], summary['first_below']) == (3, 3, '2026-03-28')
    assert '| 2026-03-29 Sun | closed (Sunday) |' in r.answer and '3 of 3 working days' in r.answer


def test_row30_no_stage_named_compares_all_and_follow_up_dates_the_run(tmp_path: Path):
    engine = make_engine(tmp_path)
    state = DialogState()
    r = chat(engine, FixedClassifier('operations.deviation', target_date='yesterday'), 'Why was output lower yesterday?', state)
    assert not r.needs_clarification and 'Assembly is the stage to worry about' in r.answer and 'reason has to come from the floor' in r.answer
    r = chat(engine, FixedClassifier('operations.deviation', stage='ASSEMBLY', target_date='yesterday'), 'Did it only start yesterday?', r.state)
    assert r.answer.startswith('No. Assembly has been below its same-weekday range for 6 consecutive working days, since 2026-03-25')
    assert '6 of 6 working days' in r.answer and r.tool_calls[0].name == 'production_window'


def test_row33_34_window_rows_and_cumulative_shortfall(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.deviation', stage='ASSEMBLY', action='evidence'), 'Show me the production records behind the assembly drop in late March.')
    rows = r.tool_calls[0].result['rows']
    assert [x['date'] for x in rows][:3] == ['2026-03-21', '2026-03-22', '2026-03-23'] and rows[1]['closed'] is True
    assert rows[4]['ASSEMBLY']['pieces'] == 394 and rows[4]['ASSEMBLY']['status'] == 'below'
    assert '| 2026-03-25 Wed | 394 (below 702–901) |' in r.answer
    engine = make_engine(tmp_path)
    state = DialogState()
    r = chat(engine, FixedClassifier('operations.deviation', stage='ASSEMBLY', target_date='2026-03-25'), 'How many pieces has assembly lost since 25 March compared with normal?', state)
    summary = r.tool_calls[0].result['summary'][0]
    assert (summary['total_pieces'], summary['shortfall_vs_same_weekday_mean'], summary['shortfall_vs_prior_working_day_mean']) == (2553, 2108, 2096)
    assert '2,553 pieces in total' in r.answer and '410 fewer' not in r.answer
    r = chat(engine, FixedClassifier('operations.deviation', stage='ASSEMBLY', action='explain'), 'What baseline did you use?', r.state)
    assert r.answer.startswith('Two baselines') and 'Same-weekday band' in r.answer and 'Prior working-day mean' in r.answer and '2,108 short by baseline 1' in r.answer


def test_row32_workshop_hypothesis_is_looked_up_not_clarified(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.deviation', stage='ASSEMBLY'), 'Assembly has been low since 25 March. Is it because the OldMill workshop was suspended?')
    assert not r.needs_clarification and 'OldMill' in r.answer and 'SUSPENDED' in r.answer and 'cannot confirm or rule out' in r.answer
    assert any(c.name == 'list_workshops' for c in r.tool_calls)


def test_row37_total_output_lists_stages_and_never_sums(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.output', target_date='2026-03-31'), 'What was the factory’s total output on 31 March?')
    assert r.answer.startswith('Recorded output on 2026-03-31 (Tuesday) by stage: knitting 905; assembly 455; washing 732; packing 657 pieces.')
    assert 'not added together' in r.answer and '2749' not in r.answer and '2,749' not in r.answer


def test_row37_followup_period_average_and_the_split_around_the_run(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.output', stage='ASSEMBLY'), 'What was the average daily assembly output in March?')
    agg = r.tool_calls[0].result['summary'][0]
    assert (agg['working_days'], agg['sundays_closed'], agg['mean_per_working_day']) == (26, 5, 704.8)
    assert (agg['run_start'], agg['run_days'], agg['mean_before_run'], agg['mean_from_run']) == ('2026-03-25', 6, 788.6, 425.5)
    assert 'Average 704.8 pieces per working day over 26 working days (5 Sundays closed)' in r.answer and '788.6/day before 2026-03-25, 425.5/day from 2026-03-25 on' in r.answer
    assert 'the table keeps the 8 working days outside their range' in r.answer   # a month is not tabulated unasked


def test_row16_risk_words_attach_the_queue_view_to_a_summary(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.summary', {})), 'Which orders are most at risk of missing their committed delivery dates today, and what should I act on first?')
    assert 'Queue view: 8 overdue' in r.answer and 'Act first on: ORD-107' in r.answer


def test_rows10_18_described_orders_get_the_rule_not_a_candidate_list(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.compare', reference='ambiguous'), 'Two customer orders need the same knitting machines this week. Which should we schedule first, and what is the impact on the other order?')
    assert not r.needs_clarification and 'does not record machines' in r.answer and 'expedite' in r.answer
    r = chat(make_engine(tmp_path), FixedClassifier('order.prioritize', window_days=0), 'An order is due tomorrow but is already packed; another is due in five days with missing yarn. Which is the higher-priority exception?')
    assert not r.needs_clarification and r.answer.startswith('Deadline alone does not decide this') and '1. ORD-' not in r.answer


def test_row38_future_date_is_answered_with_the_date_boundary(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.deviation', stage='ASSEMBLY', target_date='2026-04-03'), 'Why was assembly output low on 3 April?')
    assert r.answer.startswith('No record can exist for 2026-04-03: the business date is 2026-04-01 and the log ends 2026-03-31.')
    assert 'insufficient baseline' not in r.answer


def test_premise_correction_when_the_stated_figure_differs_from_the_record(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('operations.normality', stage='ASSEMBLY', target_date='2026-03-26', observed_output=300), 'Assembly made 300 pieces on 26 March; is that normal?')
    assert r.answer.startswith('The record shows 464 pieces on 2026-03-26, not 300.')


# ---------------------------------------------------------------- rows 1, 7, 9, 11, 17, 19, 35: orders
def test_row1_ambiguous_late_order_lists_the_overdue_candidates(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.lookup', reference='ambiguous'), 'What is the status of the order that was late yesterday?')
    assert r.needs_clarification and r.selected_order_id is None
    assert r.answer.startswith('Which one? 8 active orders are overdue as of 2026-04-01') and 'ORD-107' in r.answer and 'ORD-093' in r.answer
    assert r.tool_calls[0].name == 'search_orders' and r.tool_calls[0].result['candidates'][0]['days_to_due'] == -16


def test_row7_overdue_order_states_working_days_after_due(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.risk', order_ids=['ORD-093']), 'Will ORD-093 be late?')
    risk = r.tool_calls[-1].result
    assert risk['days_past_due'] == 3 and risk['late_days_best'] == 8 and risk['best_date'] == '2026-04-07'
    assert 'Already overdue: due 2026-03-29, 3 days ago' in r.answer and '8 working days after the due date' in r.answer


def test_row9_compare_with_criteria_ranks_by_risk_without_asking(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.compare', order_ids=['ORD-005', 'ORD-021'], action='rank', comparison_fields=['due_date', 'current_stage', 'last_activity_date', 'status']),
             'Compare ORD-005 and ORD-021: which has the higher delivery risk, considering due date, current production stage, last update and recorded blockers?')
    assert not r.needs_clarification and 'Higher delivery risk: ORD-005' in r.answer
    assert 'ORD-021: no delivery risk — status COMPLETE' in r.answer and 'Blockers: not recorded' in r.answer
    assert [c.name for c in r.tool_calls][-1] == 'rank_comparison'


def test_row11_hypothetical_policy_question_gets_the_rule(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.compare', reference='ambiguous'), 'A VIP customer order is due later than a regular customer order. Should VIP status override the earlier deadline?')
    assert not r.needs_clarification and 'VIP status alone should not override' in r.answer and 'Which order do you mean' not in r.answer


def test_row17_top_three_survives_the_window_clarification(tmp_path: Path):
    engine = make_engine(tmp_path)
    state = DialogState()
    r = chat(engine, FixedClassifier('order.prioritize'), 'Which three production exceptions require escalation before today’s morning meeting, and why?', state)
    assert r.needs_clarification and 'next seven days' in r.answer
    r = chat(engine, FixedClassifier('order.prioritize', window_days=0), 'Today only.', r.state)
    assert r.answer.startswith('Top 3 of 9') and '\n4. ORD-' not in r.answer and '6 more in the window' in r.answer and 'Action:' in r.answer


def test_row19_history_question_is_declined_with_the_reason(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.prioritize', window_days=0), 'What changed since yesterday’s exception list, and which issues have been resolved, worsened or newly emerged?')
    assert 'no dated exception snapshots' in r.answer and r.tool_calls[0].name == 'explain_no_data' and '1. ORD-' not in r.answer


def test_row35_stage_flow_rules_out_a_downstream_cause(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('order.risk', order_ids=['ORD-005'], action='explain'), 'Is ORD-005 delayed because of the assembly drop?')
    assert 'Not past due, not delayed yet: due 2026-04-20' in r.answer
    assert 'still at knitting, before assembly, so an assembly problem cannot have affected it yet' in r.answer


# ---------------------------------------------------------------- rows 42-59: actions (chase and summary run through the planner path, converse())
def test_row42_customer_named_chase_lists_that_customers_orders(tmp_path: Path):
    engine = make_engine(tmp_path)
    state = DialogState(active_order='ORD-002')
    r = chat(engine, ScriptedPlanner(('execution.chase', {'customer': 'TrendCart', 'action': 'draft'})), 'Chase up the TrendCart order.', state)
    assert r.needs_clarification and r.answer.startswith('Which TrendCart order should I chase?') and 'ORD-002' not in r.answer
    assert set(r.state.pending_clarification.candidates) == {'ORD-005', 'ORD-017', 'ORD-020', 'ORD-082', 'ORD-096', 'ORD-120'}
    assert r.tool_calls[0].name == 'search_orders' and all('days_to_due' in c for c in r.tool_calls[0].result['candidates'])


def test_row44_idle_claim_is_checked_before_drafting(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'order_ids': ['ORD-103'], 'action': 'draft'})), 'ORD-103 hasn’t moved in a week. Chase it up.')
    assert r.needs_clarification and 'last active 2026-03-30, 2 days ago, not a week' in r.answer and 'Do you still want me to draft' in r.answer
    assert not r.state.chase_drafts


def test_row45_send_straight_away_states_the_rule_first(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('execution.chase', {'order_ids': ['ORD-107'], 'action': 'send'})), 'Send the chase-up for ORD-107 straight away, no need to show me first.')
    assert r.answer.startswith('I cannot send without showing you the draft first') and not r.confirmation_required
    assert 'Which draft should I preview' not in r.answer and not any(c.name == 'send_chase' for c in r.tool_calls)


def test_row47_customer_named_note_asks_which_order(tmp_path: Path):
    engine = make_engine(tmp_path)
    state = DialogState(active_order='ORD-108')
    r = chat(engine, FixedClassifier('execution.note', customer='Maple & Co', text='hold off promising a new delivery date'), 'Add a note to the Maple & Co order: hold off promising a new delivery date.', state)
    assert r.needs_clarification and r.answer.startswith('Which Maple & Co order?') and 'ORD-083' in r.answer and 'ORD-093' in r.answer and 'ORD-108' not in r.answer
    assert not r.confirmation_required


def test_row48_cancellation_is_refused_and_offered_as_a_note(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('execution.note', order_ids=['ORD-029'], text='cancelled; take it off the schedule'), 'Record that ORD-029 is cancelled and take it off the schedule.')
    assert r.answer.startswith('I cannot cancel or remove orders') and r.confirmation_required and 'Internal note for ORD-029' in r.answer


def test_row49_workshop_mismatch_offers_eligible_active_workshops(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('execution.note', order_ids=['ORD-103'], text='decision: send ORD-103 to QuickStitch'), 'Record my decision to send ORD-103 to QuickStitch.')
    assert r.needs_clarification and 'QuickStitch (W1) makes TOPS only; ORD-103 is ACCESSORIES' in r.answer
    assert 'SteadyHands' in r.answer and 'OldMill' not in r.answer and not r.confirmation_required


def test_row59_compound_reminder_condition_asks_which(tmp_path: Path):
    r = chat(make_engine(tmp_path), FixedClassifier('execution.reminder', order_ids=['ORD-103'], condition='no_reply', deadline='tomorrow 5 pm'),
             'If ORD-103 still hasn’t finished assembly by 5 p.m. tomorrow, and the assembly supervisor still hasn’t confirmed a recovery plan, remind me.')
    assert r.needs_clarification and 'one condition per reminder' in r.answer and not r.confirmation_required


# ---------------------------------------------------------------- the summary lead (row 3-5 style "how are we doing" questions)
def test_summary_leads_with_a_readable_sentence(tmp_path: Path):
    r = chat(make_engine(tmp_path), ScriptedPlanner(('order.summary', {})), 'How are the orders doing?')
    assert r.answer.startswith('As of 2026-04-01: 34 orders in progress, 8 overdue (ORD-107') and '52 of 86 completed orders on time (60.5%)' in r.answer
