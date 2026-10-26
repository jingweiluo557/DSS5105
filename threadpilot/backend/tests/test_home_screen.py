"""The GM home screen payload (docs/CEO_INTERFACE_REVIEW.md): status line, decision cards, health, pulse.

Pure functions over the seed snapshot (business date 2026-04-01, the planted assembly drop), plus the two endpoints
the frontend reads: /api/dashboard/home and the forecast line on /api/scheduling/risk rows."""
from app.services import alert_policy as ap
from app.services import home_service as hs
from app.workflow_tools import DataTools
from tests.test_workflow import DATA, NOW
from .test_api import client  # noqa: F401  (fixture)


def snapshot():
    data, _ = DataTools(DATA).queue_snapshot(NOW)
    return data


def test_status_line_is_red_and_quotes_three_facts():
    h = hs.home(snapshot(), NOW)
    assert h['status']['colour'] == 'red' and h['alerts']['P1'] >= 2
    assert h['status']['facts'][0] == f"{h['counts']['overdue']} overdue"
    assert h['status']['facts'][1].startswith('Assembly -') and 'days' in h['status']['facts'][1]
    assert h['status']['facts'][2] == '3 decisions need you' and h['status']['date_label'] == 'Wed 1 Apr'


def test_decisions_lead_with_p1_one_card_per_entity_and_one_button_each():
    h = hs.home(snapshot(), NOW)
    cards = h['decisions']
    assert len(cards) == 3 and all(c['tier'] == ap.P1 for c in cards)
    assert cards[0]['kind'] == 'stage_drop' and cards[0]['action'] == {'label': 'Ask the floor', 'kind': 'chat', 'message': cards[0]['action']['message']}
    assert 'assembly department' in cards[0]['action']['message'] and 'Show the draft before sending' in cards[0]['action']['message']
    assert {c['kind'] for c in cards[1:]} == {'will_miss'} and all(c['action']['kind'] == 'route' and c['action']['value'].startswith('risk?id=') for c in cards[1:])
    assert len({c['entity'] for c in cards}) == 3 and h['more_waiting'] >= 20


def test_stage_card_and_status_line_quote_the_same_pulse_numbers():
    h = hs.home(snapshot(), NOW)
    assembly = next(p for p in h['pulse'] if p['stage'] == 'ASSEMBLY')
    assert assembly['status'] == 'below' and assembly['below_days'] >= 3 and assembly['band']['samples'] == 8
    card = h['decisions'][0]
    assert card['title'] == f"Assembly {-assembly['change_pct']}% below range"
    assert card['lines'][0].startswith(f"{assembly['below_days']} working days below")
    assert h['status']['facts'][1] == f"Assembly {assembly['change_pct']}% for {assembly['below_days']} days"
    assert all(p['status'] == 'within' for p in h['pulse'] if p['stage'] != 'ASSEMBLY')


def test_health_uses_one_vocabulary_and_matches_the_counts():
    h = hs.home(snapshot(), NOW)
    health = h['health']
    assert health['late'] == h['counts']['overdue'] == 8
    assert health['late'] + health['at_risk'] + health['on_track'] + health['unknown'] == health['active'] == h['counts']['in_progress'] == 34
    assert health['on_time_rate'] == 57 and health['on_time_basis'].startswith('20 of 35')


def test_green_status_when_nothing_flags():
    counts = {'overdue': 0, 'due_today': 0, 'idle': 0, 'in_progress': 10, 'total': 10}
    line = hs.status_line([], counts, [], [], NOW.date())
    assert line['colour'] == 'green' and line['facts'] == ['0 overdue', 'no decisions waiting']


def test_home_endpoint_and_forecast_line_on_risk_rows(client):
    home = client.get('/api/dashboard/home').json()
    assert home['status']['colour'] in ('red', 'amber', 'green') and len(home['decisions']) <= 3 and len(home['pulse']) == 4
    assert home['health']['late'] == home['counts']['overdue']
    rows = client.get('/api/scheduling/risk').json()['orders']
    assert rows and all('forecast' in r for r in rows)
    first = next(r for r in rows if r['forecast'])
    assert 0 <= first['forecast']['delay_probability'] <= 1 and len(first['forecast']['completion_range_80pct']) == 2
