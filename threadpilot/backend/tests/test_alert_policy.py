"""Alert policy: what interrupts the manager, and what never does. Pure functions over the seed snapshot."""
from datetime import timedelta
from pathlib import Path

from app.services import alert_policy as ap
from app.workflow_tools import DataTools
from tests.test_workflow import DATA, NOW


def snapshot():
    data, _ = DataTools(DATA).queue_snapshot(NOW)
    return data


def test_detection_finds_the_planted_assembly_drop_and_near_due_misses():
    alerts = ap.detect(snapshot(), NOW)
    keys = {a.key: a for a in alerts}
    assert keys['stage_drop:ASSEMBLY'].tier == ap.P1 and len(keys['stage_drop:ASSEMBLY'].evidence) == 3
    assert 'will_miss:ORD-108' in keys and keys['will_miss:ORD-108'].tier == ap.P1
    assert all(a.tier == ap.P2 for a in alerts if a.kind == 'overdue') and 'overdue:ORD-107' in keys
    assert not any(a.kind == 'low_day' and a.entity == 'ASSEMBLY' for a in alerts), 'a sustained drop replaces the single-day watch item'
    assert alerts == sorted(alerts, key=lambda a: ({ap.P1: 0, ap.P2: 1, ap.P3: 2}[a.tier], -a.score, a.key))


def test_gate_sends_p1_at_once_batches_p2_and_never_re_emails_an_unresolved_item():
    alerts = ap.detect(snapshot(), NOW)
    first = ap.gate(alerts, [], NOW)
    channels = {d.alert.key: d.channel for d in first}
    assert channels['stage_drop:ASSEMBLY'] == 'email_now' and channels['overdue:ORD-107'] == 'digest'
    assert sum(1 for d in first if d.channel == 'email_now') <= ap.MAX_P1_PER_DAY
    history = [{'key': d.alert.key, 'tier': d.alert.tier, 'score': d.alert.score, 'sent_at': NOW.isoformat(), 'channel': d.channel} for d in first if d.channel in ('email_now', 'digest')]
    # same day, an hour later: everything already reported is suppressed
    later = ap.gate(alerts, history, NOW + timedelta(hours=1))
    assert all(d.channel == 'suppressed' for d in later if d.alert.tier != ap.P3)
    # next day, nothing escalated: the open P1s are reminded in the digest, not re-emailed
    next_day = ap.gate(alerts, history, NOW + timedelta(hours=26))
    assert not any(d.channel == 'email_now' for d in next_day)
    assert {d.channel for d in next_day if d.alert.tier == ap.P1} == {'digest'}


def test_escalation_and_shelving():
    alerts = ap.detect(snapshot(), NOW)
    drop = next(a for a in alerts if a.key == 'stage_drop:ASSEMBLY')
    history = [{'key': drop.key, 'tier': drop.tier, 'score': drop.score - ap.ESCALATION_STEP, 'sent_at': NOW.isoformat(), 'channel': 'email_now'}]
    assert next(d for d in ap.gate([drop], history, NOW + timedelta(hours=2))).channel == 'email_now', 'a worse score re-alerts'
    shelved = ap.gate([drop], [], NOW, {'stage_drop': (NOW + timedelta(days=7)).isoformat()})[0]
    assert shelved.channel == 'suppressed' and 'shelved' in shelved.reason


def test_daily_cap_and_digest_timing():
    alerts = ap.detect(snapshot(), NOW)
    p1s = [a for a in alerts if a.tier == ap.P1]
    history = [{'key': f'x:{i}', 'tier': ap.P1, 'score': 90, 'sent_at': NOW.isoformat(), 'channel': 'email_now'} for i in range(ap.MAX_P1_PER_DAY)]
    assert all(d.channel == 'digest' for d in ap.gate(p1s, history, NOW + timedelta(hours=1)))
    assert ap.digest_due(NOW.replace(hour=7, minute=30), None)
    assert not ap.digest_due(NOW.replace(hour=9), NOW.replace(hour=7, minute=5))
    assert ap.digest_due(NOW.replace(hour=14, minute=1), NOW.replace(hour=7, minute=5))
    assert not ap.digest_due(NOW.replace(hour=6), None)


def test_email_leads_with_three_lines_and_says_why():
    decisions = ap.gate(ap.detect(snapshot(), NOW), [], NOW)
    mail = ap.render_email(decisions, NOW, 'Jingwei')
    body = mail['body'].splitlines()
    assert mail['subject'].startswith('[ThreadPilot P1]') and body[0] == 'Hello Jingwei,'
    assert sum(1 for line in body[2:6] if line.startswith('- ')) <= 3
    assert 'Why you got this' in mail['body'] and 'Mute' in mail['body']
    digest_only = [d for d in decisions if d.channel == 'digest']
    digest = ap.render_email(digest_only, NOW)
    assert digest['subject'].startswith('[ThreadPilot digest]') and 'Overdue:' in digest['body'] and 'High Risk:' in digest['body']


def test_ledger_round_trip(tmp_path: Path):
    from app.services.alert_delivery import AlertLedger
    ledger = AlertLedger(tmp_path / 'alerts.sqlite3')
    decisions = ap.gate(ap.detect(snapshot(), NOW), [], NOW)
    ledger.record(decisions, NOW, email_id='e1', email_status='dry_run')
    assert len(ledger.history()) == sum(1 for d in decisions if d.channel in ('email_now', 'digest'))
    ledger.shelve('overdue', '2026-04-08T23:59:59+08:00', 'manager', NOW)
    assert ledger.shelved() == {'overdue': '2026-04-08T23:59:59+08:00'}
    ledger.record_digest(NOW, ['a', 'b'], 'dry_run')
    assert ledger.last_digest() == NOW
    ledger.feedback('stage_drop:ASSEMBLY', True, 'useful', NOW)
    kpis = ledger.kpis(NOW)
    assert kpis['p1_emails_today'] == 1 and kpis['rated_useful_pct'] == 100.0
