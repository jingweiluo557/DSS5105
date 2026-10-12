"""Discovery and risk on the live backend (app/discovery.py), held to the morning-briefing engine.

Before this, the live chat could only read the saved 07:00 summary, and its "risk" was a 7-day threshold flag that could disagree
with the dashboard. These tests check that the live tools now give the SAME findings and the SAME risk level as the briefing page,
on the provided data and on simulated mornings with planted events, from CSV and from the database.

The classifier is a stand-in that returns the intent a test asks for. These tests show the server-side behaviour; they do not
measure how often a real model picks discovery.findings (see docs/evaluation.md, live backend).
"""
import asyncio
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import discovery  # noqa: E402
from app.schemas import ChatRequest, Classification, Intent, Slots  # noqa: E402
from app.services.snapshot_service import DatabaseDataTools  # noqa: E402
from app.workflow_engine import WorkflowEngine  # noqa: E402
from app.workflow_store import WorkflowStore  # noqa: E402
from app.workflow_tools import DataTools  # noqa: E402
from simulation import briefing  # noqa: E402
from simulation.simulate import simulate  # noqa: E402

SGT = timezone(timedelta(hours=8))
DATA = ROOT / 'data'


def morning(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, tzinfo=SGT)


class Fixed:
    def __init__(self, intent: str, **slots) -> None:
        self.result = Classification(intent=Intent(intent), slots=Slots(**slots), confidence=.99)

    async def classify(self, message, state, now):
        return self.result


def engine_for(tools, tmp_path: Path, now: datetime) -> WorkflowEngine:
    return WorkflowEngine(tools, WorkflowStore(tmp_path / 'wf.sqlite3'), lambda: now, None)


def ask(engine: WorkflowEngine, message: str, intent: str, session: str | None = None, **slots):
    return asyncio.run(engine.chat(ChatRequest(message=message, session_id=session), Fixed(intent, **slots)))


@pytest.fixture(scope='module')
def mornings(tmp_path_factory):
    """The provided data (1 April) and three simulated mornings. The simulator plants events, e.g. TrendCart stalls from 6 April."""
    out = {date(2026, 4, 1): DATA}
    for day in (date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 15)):
        folder = tmp_path_factory.mktemp(f'm{day.day}')
        simulate(day, out=folder)
        out[day] = folder
    return out


# ---------------------------------------------------------------- one definition of a finding
def test_live_findings_are_the_briefing_pages_findings(mornings):
    for day, folder in mornings.items():
        page = briefing.build(folder, day)
        live = DataTools(folder).findings(morning(day))
        assert [f['key'] for f in live['findings']] == [f['key'] for f in page['findings']], day
        assert [f['score'] for f in live['findings']] == [f['score'] for f in page['findings']], day
        assert live['more_findings'] == page['more_findings'] and live['status_counts'] == page['status_counts'], day


def test_the_stalled_customer_is_raised_without_being_asked(mornings, tmp_path):
    day = date(2026, 4, 9)
    response = ask(engine_for(DataTools(mornings[day]), tmp_path, morning(day)), 'Anything unusual I should know about?', 'discovery.findings')
    assert [c.name for c in response.tool_calls][0] == 'list_findings'
    assert 'All 6 active TrendCart orders have stopped moving' in response.answer
    assert 'Next step:' in response.answer and 'not a confirmed cause' in response.answer
    assert not response.confirmation_required, 'finding something never opens an action'


def test_every_finding_line_comes_from_the_tool_and_brings_its_rows(tmp_path):
    response = ask(engine_for(DataTools(DATA), tmp_path, morning(date(2026, 4, 1))), "What's wrong in the factory right now?", 'discovery.findings')
    result = response.tool_calls[0].result
    for f in result['findings']:
        assert f['title'] in response.answer and f['next_step'] in response.answer
    # tracing: each finding's rows are attached as evidence, with a link to the source row
    order_ids = {i for f in result['findings'] for i in f['order_ids']}
    attached = {e.record.get('order_id') for e in response.evidence if e.source == 'orders.csv'}
    assert order_ids <= attached
    assert any(e.source == 'production_log.csv' for e in response.evidence), 'a stage finding brings its production rows'
    # every number in a finding line is in the tool result (the model never adds one)
    tool_text = str(result)
    for line in response.answer.splitlines()[1:1 + len(result['findings'])]:
        for number in re.findall(r'\d[\d,.]*', line):
            assert number.rstrip('.,') in tool_text, (number, line)


def test_a_follow_up_has_the_top_findings_orders_to_talk_about(tmp_path):
    engine = engine_for(DataTools(DATA), tmp_path, morning(date(2026, 4, 1)))
    first = ask(engine, 'What problems do you see?', 'discovery.findings')
    top = first.tool_calls[0].result['findings'][0]
    assert first.state.last_order_ids[:len(top['order_ids'])] == top['order_ids'][:10]


def test_discovery_says_how_old_the_data_is(tmp_path):
    """On the live site the clock moves on but the data may not: the answer says what date the data runs to."""
    later = morning(date(2026, 10, 12))
    response = ask(engine_for(DataTools(DATA), tmp_path, later), 'Anything unusual?', 'discovery.findings')
    assert response.tool_calls[0].result['data_through'] == '2026-03-31'
    assert 'data up to 2026-03-31' in response.answer or 'Data runs to 2026-03-31' in response.answer


# ---------------------------------------------------------------- one definition of risk
def test_the_live_risk_level_is_the_dashboards_risk_level(mornings):
    checked = 0
    for day, folder in mornings.items():
        page = {o['order_id']: o['risk'] for o in briefing.build(folder, day)['orders']}
        tools = DataTools(folder)
        levels = tools.risk_levels(morning(day))
        for e in tools.rows('orders.csv'):
            if e.record['status'] != 'IN_PROGRESS':
                continue
            live = tools.assess_risk(e, morning(day), levels)
            assert live['risk_level'] == page[e.record['order_id']]['level'], (day, e.record['order_id'])
            assert live['expected_finish'] == page[e.record['order_id']]['expected_date']
            checked += 1
    assert checked >= 100


def test_the_risk_answer_leads_with_the_level_and_keeps_its_limits(tmp_path):
    engine = engine_for(DataTools(DATA), tmp_path, morning(date(2026, 4, 1)))
    response = ask(engine, 'Is ORD-005 at risk?', 'order.risk', order_ids=['ORD-005'])
    risk = next(c.result for c in response.tool_calls if c.name == 'assess_order_risk')
    assert response.answer.startswith(f"Risk level: {risk['risk_level'].upper()} (the same queue projection the dashboard uses).")
    assert 'not confirmed late delivery' in response.answer and 'risk_flag' not in risk
    assert risk['risk_rule'] == briefing.DEFINITIONS['risk']


def test_a_completed_order_has_no_risk_level(tmp_path):
    tools = DataTools(DATA)
    done = next(e for e in tools.rows('orders.csv') if e.record['status'] == 'COMPLETE')
    assert tools.assess_risk(done, morning(date(2026, 4, 1)))['risk_level'] == 'complete'


# ---------------------------------------------------------------- the database path and the saved briefing
def test_the_database_gives_the_same_findings_with_record_links(business_database):
    now = morning(date(2026, 4, 1))
    from_csv = DataTools(DATA).findings(now)
    from_db = DatabaseDataTools(business_database).findings(now)
    assert [f['key'] for f in from_db['findings']] == [f['key'] for f in from_csv['findings']]
    assert from_db['_evidence'] and all(e.url.startswith('/api/evidence/') and e.record_id for e in from_db['_evidence'])


def test_the_saved_07_00_briefing_carries_the_same_findings(tmp_path, business_database):
    from app.briefing_email import metadata as email_metadata
    from app.dashboard_store import metadata
    from app.forecast_store import import_forecasts, metadata as prediction_metadata
    from app.services.dashboard_service import DashboardService, forecast_asset
    from app.services.snapshot_service import snapshot
    for m in (email_metadata, metadata, prediction_metadata):
        m.create_all(business_database.engine)
    import_forecasts(business_database, forecast_asset())
    DashboardService(business_database).generate_due(snapshot(business_database, '2026-04-01'), datetime(2026, 10, 10, 7, tzinfo=SGT))
    tools = DatabaseDataTools(business_database)
    saved = tools.briefing()
    assert [f['key'] for f in saved['findings']] == [f['key'] for f in tools.findings(morning(date(2026, 4, 1)))['findings']]
    response = ask(engine_for(tools, tmp_path, morning(date(2026, 4, 1))), 'Did anything go wrong yesterday?', 'briefing.today')
    assert 'Found without being asked: 1. ' + saved['findings'][0]['title'] in response.answer


def test_discovery_reads_and_never_writes(tmp_path):
    before = {p.name: p.read_bytes() for p in DATA.glob('*.csv')}
    response = ask(engine_for(DataTools(DATA), tmp_path, morning(date(2026, 4, 1))), 'Anything unusual?', 'discovery.findings')
    assert response.state.pending_action is None
    assert {p.name: p.read_bytes() for p in DATA.glob('*.csv')} == before
