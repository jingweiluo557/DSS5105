"""Configure, initialize and check an existing CloudBase MySQL database.

Secrets are entered locally with getpass; no account creation or password resets.
"""
import argparse
from getpass import getpass
import os
from pathlib import Path
import secrets

from dotenv import dotenv_values, set_key
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.config import ROOT

CONFIG = ROOT / 'backend/.env.cloudbase'
DATABASE = 'dss5105-track1-i7gxvcy5k7ef5ac9b'
HOST = 'sg-cynosdbmysql-grp-fe15p52v.sql.tencentcdb.com'
TABLES = ('orders', 'production_log', 'workshops')


def connection_url(user: str, password: str, host: str = HOST,
                   port: int = 26794, database: str = DATABASE) -> str:
    return URL.create('mysql+pymysql', username=user, password=password,
                      host=host, port=port, database=database,
                      query={'charset': 'utf8mb4', 'connect_timeout': '10'}).render_as_string(hide_password=False)


def configure(path: Path) -> None:
    if path.exists():
        raise ValueError('Cloud configuration already exists; edit it locally instead of overwriting it.')
    app_password = getpass('threadpilot_app password (hidden): ')
    ai_password = getpass('threadpilot_ai password (hidden): ')
    if not app_password or not ai_password or app_password == ai_password:
        raise ValueError('Enter two distinct nonempty passwords.')
    values = {
        'DATABASE_URL': connection_url('threadpilot_app', app_password),
        'AI_DATABASE_URL': connection_url('threadpilot_ai', ai_password),
        'CORS_ORIGINS': '["https://jingweiluo557.github.io"]',
        'DATA_API_TOKEN': secrets.token_urlsafe(32),
        'OPENAI_API_KEY': getpass('Model API key (hidden; Enter to configure later): '),
        'OPENAI_BASE_URL': input('Model base URL [https://api.openai.com/v1]: ').strip() or 'https://api.openai.com/v1',
        'OPENAI_MODEL': input('Model name [gpt-4.1]: ').strip() or 'gpt-4.1',
        'INTENT_API_STYLE': 'responses',
        'SYNC_ENABLED': 'false',
        'BUSINESS_NOW': '2026-04-01T12:00:00+08:00',
        'PORT': '8000',
    }
    # Exclusive creation prevents accidental replacement of existing credentials.
    with path.open('x', encoding='utf-8') as stream:
        stream.write('# Private CloudBase configuration. Never commit or upload as source.\n')
    for key, value in values.items():
        set_key(str(path), key, value)
    print('Saved backend/.env.cloudbase. No connection or database changes have been made.')


def load_config(path: Path) -> None:
    if not path.exists():
        raise ValueError('Run configure first.')
    values = dotenv_values(path, interpolate=False)
    for key in ('DATABASE_URL', 'AI_DATABASE_URL'):
        url = make_url(values.get(key) or '')
        if url.drivername != 'mysql+pymysql' or url.database != DATABASE or not url.host:
            raise ValueError('Configuration must target the specified CloudBase MySQL database.')
    for key, value in values.items():
        if value is not None:
            os.environ[key] = value


def update_password(path: Path, account: str) -> None:
    """Replace only one locally saved password, keeping model settings intact."""
    if not path.exists():
        raise ValueError('Run configure first.')
    key = 'DATABASE_URL' if account == 'app' else 'AI_DATABASE_URL'
    values = dotenv_values(path, interpolate=False)
    url = make_url(values.get(key) or '')
    password = getpass(f'{url.username} current CloudBase password (hidden): ')
    if not password or not password.isascii() or any(c.isspace() for c in password):
        raise ValueError('Enter the password using English letters, digits and symbols without whitespace.')
    if password != getpass('Repeat password (hidden): '):
        raise ValueError('Passwords do not match.')
    set_key(str(path), key, url.set(password=password).render_as_string(hide_password=False))
    print('Local password updated. Cloud account password and other settings were not changed.')


def initialize_cloud(deploy_user: str) -> None:
    from alembic import command
    from alembic.config import Config
    from app.db.init_db import initialize

    application_url = os.environ['DATABASE_URL']
    password = getpass(f'{deploy_user} migration password (hidden, not saved): ')
    if not password:
        raise ValueError('Migration password is required.')
    migration_url = make_url(application_url).set(username=deploy_user, password=password)
    engine = create_engine(migration_url)
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        os.environ['DATABASE_URL'] = migration_url.render_as_string(hide_password=False)
        command.upgrade(Config(str(ROOT / 'backend/alembic.ini')), 'head')
    finally:
        os.environ['DATABASE_URL'] = application_url
        engine.dispose()
    initialize([ROOT / 'data' / f'{name}.csv' for name in TABLES], migrate=False)
    print('Schema migration and demo import completed. Local database was not changed.')


def check() -> None:
    for key, label in [('DATABASE_URL', 'application'), ('AI_DATABASE_URL', 'AI')]:
        engine = create_engine(os.environ[key])
        try:
            with engine.connect() as conn:
                for table in TABLES:
                    count = conn.execute(text(f'SELECT COUNT(*) FROM `{table}`')).scalar_one()
                    print(f'{label}: {table}: {count} rows')
        finally:
            engine.dispose()
    print('Both accounts can read the demo tables. Write restrictions require a separate grant review.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['configure', 'initialize', 'check', 'password'])
    parser.add_argument('--account', choices=['app', 'ai'], default='app')
    parser.add_argument('--deploy-user', default='threadpilot_app')
    args = parser.parse_args()
    try:
        if args.action == 'configure':
            configure(CONFIG)
        elif args.action == 'password':
            update_password(CONFIG, args.account)
        else:
            load_config(CONFIG)
            if args.action == 'initialize':
                initialize_cloud(args.deploy_user)
            check()
    except (SQLAlchemyError, ValueError, OSError):
        # Do not print exception strings containing URLs, SQL parameters or secrets.
        raise SystemExit('Cloud operation failed. Check local configuration, connectivity and account privileges; credentials were not printed.') from None


if __name__ == '__main__':
    main()
