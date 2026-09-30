"""Persistent deployment credentials and explicit environment overrides."""
from unittest.mock import MagicMock

import pytest

from scripts import provision_mysql


@pytest.mark.parametrize('override', [False, True])
def test_provision_reads_saved_credentials(tmp_path, monkeypatch, override):
    config_dir = tmp_path / 'backend'
    config_dir.mkdir()
    saved_app = 'saved_app_password_1234567890'
    saved_ai = 'saved_ai_password_12345678901'
    explicit_app = 'explicit_app_password_1234567'
    (config_dir / '.env').write_text(
        f'MYSQL_APP_PASSWORD={saved_app}\nMYSQL_AI_PASSWORD={saved_ai}\n'
        'DATA_API_TOKEN=saved-management-token\n', encoding='utf-8'
    )
    for name in ('MYSQL_APP_PASSWORD', 'MYSQL_AI_PASSWORD', 'DATA_API_TOKEN',
                 'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DATABASE', 'MYSQL_APP_USER', 'MYSQL_AI_USER'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('MYSQL_ROOT_PASSWORD', 'test-root-password')
    # Track environment mutation performed by the deployment script for cleanup.
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    if override:
        monkeypatch.setenv('MYSQL_APP_PASSWORD', explicit_app)
    monkeypatch.setattr(provision_mysql, 'ROOT', tmp_path)
    connect = MagicMock()
    monkeypatch.setattr(provision_mysql.pymysql, 'connect', connect)
    monkeypatch.setattr(provision_mysql.command, 'upgrade', MagicMock())
    provision_mysql.main()
    cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.execute.assert_any_call(
        'ALTER USER %s@%s IDENTIFIED BY %s',
        ('threadpilot_app', '%', explicit_app if override else saved_app),
    )
    cursor.execute.assert_any_call(
        'ALTER USER %s@%s IDENTIFIED BY %s', ('threadpilot_ai', '%', saved_ai)
    )
