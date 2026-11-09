"""Two failures found while recording the Sprint 3 demo (9 Nov 2026), now regression tests."""
from pathlib import Path

from tests.test_sprint2_fixes import ScriptedPlanner, chat
from tests.test_workflow import make_engine


def test_a_description_narrows_the_open_candidate_list(tmp_path: Path):
    """'The vest one' after 'Chase the order with 1500 tops' is ORD-120 of the three listed, not every vest order on file."""
    engine = make_engine(tmp_path)
    planner = ScriptedPlanner(('execution.chase', {'action': 'draft', 'quantity': 1500, 'product': 'tops'}),
                              ('execution.chase', {'action': 'draft', 'product': 'Vest'}))
    r = chat(engine, planner, 'Chase the order with 1500 tops')
    assert r.needs_clarification and 'ORD-120' in r.answer and 'ORD-099' in r.answer and 'ORD-081' in r.answer
    r = chat(engine, planner, 'The vest one.', r.state)
    assert 'the vest order among the 3 listed: ORD-120' in r.answer
    assert 'ORD-020' not in r.answer and 'ORD-045' not in r.answer
    assert not any(c.name == 'send_chase' and c.executed for c in r.tool_calls)


def test_a_stuck_since_last_week_claim_is_checked_before_drafting(tmp_path: Path):
    """ORD-029 moved today; 'stuck at washing since last wk' is answered with the record and a question, not a draft
    that says 'no recorded activity since today (0 days)'."""
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-029'], 'reference': 'explicit', 'department': 'WASHING'})),
             'Chase ORD-029, stuck at washing since last week')
    assert r.needs_clarification and r.answer.startswith('ORD-029 was last active 2026-04-01, today, not since last week')
    assert 'Draft' not in r.answer
    # a true claim still drafts straight away
    r = chat(make_engine(tmp_path / 'b'), ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-005'], 'reference': 'explicit', 'department': 'KNITTING'})),
             "ORD-005 hasn't moved in a week, chase knitting")
    assert 'ORD-005' in r.answer and 'was last active' not in r.answer   # no premise question (the test engine has no mailbox, so it asks for a recipient)
