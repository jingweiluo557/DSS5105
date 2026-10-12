"""The brief asks for ONE explicit definition of 'normal'. The morning briefing (simulation/briefing.py) and the backend's
chat tool (DataTools.normality) are separate code, so this test holds them to the same numbers: the same eight same-weekday
samples, the same mean, the same band, the same verdict, on the provided data and on simulated days."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]          # the threadpilot/ folder
sys.path.insert(0, str(ROOT))

from app.schemas import Slots  # noqa: E402
from app.workflow_tools import BAND_MIN_PCT, BAND_SD, DataTools  # noqa: E402
from simulation import briefing  # noqa: E402
from simulation.simulate import simulate  # noqa: E402
from simulation.workdays import prev_working  # noqa: E402

STAGES = ('KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING')
VERDICT = {'within': 'normal', 'below': 'below', 'above': 'above'}


@pytest.fixture(scope='module')
def folders(tmp_path_factory):
    out = {date(2026, 4, 1): ROOT / 'data'}
    for day in (date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 15)):
        folder = tmp_path_factory.mktemp(f'day{day.day}')
        simulate(day, out=folder)
        out[day] = folder
    return out


def test_the_two_codebases_share_the_same_constants():
    assert (BAND_SD, BAND_MIN_PCT) == (briefing.BAND_SD, briefing.BAND_MIN_PCT) == (1.5, 0.05)
    assert briefing.BASELINE_WEEKS == 8 and briefing.MIN_SAMPLES == 3


def test_backend_and_briefing_agree_on_normal(folders):
    checked = 0
    for business_date, folder in folders.items():
        b = briefing.build(folder, business_date)
        tools = DataTools(folder)
        now = datetime(business_date.year, business_date.month, business_date.day, 8, tzinfo=timezone(timedelta(hours=8)))
        for stage in STAGES:
            expected = b['stages'][stage]['yesterday']
            if expected['status'] in ('insufficient', 'no_data'):
                continue
            data, _ = tools.normality(Slots(stage=stage, target_date=prev_working(business_date).isoformat()), now)
            tag = f'{business_date} {stage}'
            assert data['sample_count'] == expected['samples'] == 8, tag
            assert data['output'] == expected['observed'], tag
            assert data['mean'] == pytest.approx(expected['mean'], abs=0.06), tag
            assert data['band_low'] == pytest.approx(expected['low'], abs=0.11), tag
            assert data['band_high'] == pytest.approx(expected['high'], abs=0.11), tag
            assert VERDICT[data['status']] == expected['status'], tag
            checked += 1
    assert checked >= 12          # three or more mornings x four stages


def test_the_backend_tool_states_the_rule(folders):
    now = datetime(2026, 4, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    data, _ = DataTools(folders[date(2026, 4, 1)]).normality(Slots(stage='PACKING', target_date='2026-03-31'), now)
    assert data['rule'] == 'normal band = mean +/- max(1.5 x standard deviation, 5% of the mean)'
    assert data['band_low'] < data['mean'] < data['band_high'] and data['minimum'] <= data['maximum']


def test_the_team_dashboard_uses_the_same_normal(business_database):
    """The live dashboard (app/services/dashboard_service.py) is a third piece of code that judges a stage's output.
    It must reach the same mean, band and verdict as the chat tool, so the GM never sees two answers to one question."""
    from app.services.dashboard_service import BASELINE_WEEKS, MIN_SAMPLES, analyze
    from app.services.snapshot_service import snapshot

    assert (BASELINE_WEEKS, MIN_SAMPLES) == (briefing.BASELINE_WEEKS, briefing.MIN_SAMPLES) == (8, 3)
    result = analyze(snapshot(business_database, '2026-04-01'))
    tools = DataTools(ROOT / 'data')
    now = datetime(2026, 4, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    checked = 0
    for row in result['production']:
        if row['status'] == 'insufficient':
            continue
        data, _ = tools.normality(Slots(stage=row['stage'], target_date=row['date']), now)
        tag = f"{row['stage']} {row['date']}"
        assert data['sample_count'] == row['samples'], tag
        assert data['output'] == row['pieces'], tag
        assert row['baseline'] == pytest.approx(data['mean'], abs=0.006), tag
        assert row['low'] == pytest.approx(data['band_low'], abs=0.06), tag
        assert row['high'] == pytest.approx(data['band_high'], abs=0.06), tag
        assert VERDICT[data['status']] == {'within': 'normal'}.get(row['status'], row['status']), tag
        checked += 1
    assert checked == 4          # all four stages have enough history on the provided data
