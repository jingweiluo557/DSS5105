"""Back up rows, apply an additive migration and verify existing data unchanged.

Uses only the named project's private cloud configuration. Never imports seeds.
"""
import argparse
import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from .cloudbase import CONFIG, DATABASE, load_config
from app.config import ROOT

def snapshot(connection):
    result = {}
    for name in sorted(inspect(connection).get_table_names()):
        quoted = connection.dialect.identifier_preparer.quote(name)
        rows = [dict(row) for row in connection.execute(text('SELECT * FROM ' + quoted)).mappings()]
        serialized = sorted(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) for row in rows)
        result[name] = {'rows': rows, 'count': len(rows),
            'sha256': hashlib.sha256('\n'.join(serialized).encode()).hexdigest()}
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    load_config(CONFIG)
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    output = ROOT / '.build' / ('cloudbase-migration-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    with engine.connect() as connection:
        before = snapshot(connection)
        version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    # Private, local snapshot: includes data and CREATE TABLE statements for recovery.
    with engine.connect() as connection:
        schema = {name: connection.execute(text('SHOW CREATE TABLE ' + connection.dialect.identifier_preparer.quote(name))).fetchone()[1] for name in before}
    with gzip.open(output / 'backup.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump({'database': DATABASE, 'version': version, 'schema': schema, 'tables': before}, stream, ensure_ascii=False, default=str)
    print('Backup saved locally. Current revision:', version)
    if not args.apply:
        print('Read-only check complete. No database changes.')
        return
    if version not in ('0008_ai_morning', '0009_cloud_mail', '0010_cloud_alerts'):
        raise ValueError('Unexpected starting revision; review migrations before applying.')
    command.upgrade(Config(str(ROOT / 'backend/alembic.ini')), '0010_cloud_alerts')
    with engine.connect() as connection:
        after = snapshot(connection)
        updated = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    unchanged = all(after.get(name, {}).get('sha256') == table['sha256'] for name, table in before.items() if name != 'alembic_version')
    report = {'database': DATABASE, 'from': version, 'to': updated, 'existing_data_unchanged': unchanged,
        'new_tables': sorted(set(after) - set(before)), 'backup': 'backup.json.gz',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'before': {k:{x:v[x] for x in ('count','sha256')} for k,v in before.items()},
        'after': {k:{x:v[x] for x in ('count','sha256')} for k,v in after.items()}}
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Revision:', updated, '| Existing tables unchanged:', unchanged, '| New tables:', len(report['new_tables']))
    print('Evidence:', output)
    if not unchanged: raise ValueError('Existing data changed during verification; inspect report before deploying.')

if __name__ == '__main__':
    try:
        main()
    except (SQLAlchemyError, ValueError, OSError):
        raise SystemExit('Cloud schema operation stopped. Check connectivity, privileges and local verification files; no credentials printed.') from None
