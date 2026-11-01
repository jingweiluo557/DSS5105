# Cloud alert persistence

With `WORKFLOW_STORAGE=database`, alert history, shelves, digest timestamps and manager feedback use the existing MySQL database. SQLite remains available for local mode and explicit test ledger paths. HTTP responses and alert policy rules are unchanged.

Apply Alembic revision `0010_cloud_alerts` before uploading the new backend ZIP. It adds four tables and does not modify business or mail data. `python -m scripts.upgrade_cloud_schema --apply` backs up the database first and compares existing rows afterward. Runtime credentials require CRUD on the new tables; runtime startup never creates them.

The MySQL scheduler holds a named lock during alert evaluation and delivery so overlapping function instances do not simultaneously send the same alert. Mail delivery is still not exactly-once across a process crash between provider acceptance and ledger recording. `ALERT_EMAILS_ENABLED` retains its existing default of false; this storage migration does not enable additional email sends.

Existing local SQLite alert history is not automatically imported. The deployed October 24 backend predates this alert ledger; the cloud tables start empty. Do not discard any local historical ledger that needs a separate import.

Validation on October 26: 241 backend tests passed, one skipped; local migration to head passed; CloudBase migrated from `0009_cloud_mail` to `0010_cloud_alerts` with all existing table row hashes unchanged. Cloud MySQL read access and KPI queries passed. Private backups remain under ignored `.build/cloudbase-migration-*` directories.
