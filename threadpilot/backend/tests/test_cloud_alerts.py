"""Cloud ledger parity and persistence, without sending mail."""
from datetime import timedelta
from app.config import Settings
from app.services.alert_delivery import AlertLedger, AlertDelivery
from app.services.sql_alert_ledger import SQLAlertLedger
from app.services import alert_policy
from .test_alert_policy import snapshot, NOW


def test_cloud_ledger_matches_local_and_survives_restart(tmp_path, business_database):
    settings = Settings(_env_file=None, workflow_storage='database', database_url=str(business_database.engine.url))
    cloud = SQLAlertLedger(settings)
    local = AlertLedger(tmp_path / 'local-alerts.sqlite3')
    items = alert_policy.gate(alert_policy.detect(snapshot(), NOW), [], NOW)
    for ledger in (cloud, local):
        ledger.record(items, NOW, 'one-email', 'dry_run')
        ledger.shelve('overdue', '2026-04-08T23:59:59+08:00', 'manager', NOW)
        ledger.shelve('overdue', '2026-04-09T23:59:59+08:00', 'manager', NOW)
        ledger.record_digest(NOW, ['a', 'b'], 'dry_run')
        ledger.record_digest(NOW + timedelta(hours=7), ['c'], 'dry_run')
        ledger.feedback('stage_drop:ASSEMBLY', True, 'useful', NOW)
        ledger.feedback('overdue:ORD-107', False, 'seen', NOW)
    restarted = SQLAlertLedger(settings)
    assert sorted(restarted.history(), key=lambda x: x['key']) == sorted(local.history(), key=lambda x: x['key'])
    assert restarted.shelved() == local.shelved()
    assert restarted.last_digest() == local.last_digest()
    assert restarted.kpis(NOW) == local.kpis(NOW)
    assert all(d.channel != 'email_now' for d in alert_policy.gate(
        alert_policy.detect(snapshot(), NOW), restarted.history(), NOW + timedelta(hours=1), restarted.shelved()))


def test_cloud_delivery_never_creates_local_ledger(tmp_path, business_database):
    path = tmp_path / 'not-created' / 'workflow.sqlite3'
    settings = Settings(_env_file=None, workflow_storage='database', workflow_db=path, database_url=str(business_database.engine.url))
    assert isinstance(AlertDelivery(settings).ledger, SQLAlertLedger)
    assert not path.parent.exists()


def test_empty_cloud_kpis(business_database):
    ledger = SQLAlertLedger(Settings(_env_file=None, workflow_storage='database', database_url=str(business_database.engine.url)))
    assert ledger.history() == [] and ledger.shelved() == {} and ledger.last_digest() is None
    assert ledger.kpis(NOW)['rated_useful_pct'] is None
