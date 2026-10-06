"""Cloud configuration must stay isolated from local credentials."""
from sqlalchemy.engine import make_url
from scripts import cloudbase
import pytest


def test_cloud_url_encodes_password_and_hyphenated_database():
    url = make_url(cloudbase.connection_url('threadpilot_app', 'test@:/#%password'))
    assert url.password == 'test@:/#%password'
    assert url.database == cloudbase.DATABASE
    assert url.port == 26794


def test_refuses_wrong_database(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///local.db')
    path = tmp_path / '.env.cloudbase'
    path.write_text("DATABASE_URL='mysql+pymysql://u:p@cloud/other'\n")
    with pytest.raises(ValueError):
        cloudbase.load_config(path)
    import os
    assert os.environ['DATABASE_URL'] == 'sqlite:///local.db'


def test_cloud_credentials_do_not_interpolate(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_SUFFIX', 'should-not-replace')
    url = cloudbase.connection_url('threadpilot_app', '${SECRET_SUFFIX}')
    path = tmp_path / '.env.cloudbase'
    path.write_text(f"DATABASE_URL='{url}'\nAI_DATABASE_URL='{url}'\n")
    cloudbase.load_config(path)
    import os
    assert make_url(os.environ['DATABASE_URL']).password == '${SECRET_SUFFIX}'


def test_cors_preflight_for_pages(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('CORS_ORIGINS', '["https://jingweiluo557.github.io"]')
    client = TestClient(create_app())
    headers = {'Origin': 'https://jingweiluo557.github.io',
               'Access-Control-Request-Method': 'POST',
               'Access-Control-Request-Headers': 'Content-Type'}
    response = client.options('/api/v1/workflow/chat/stream', headers=headers)
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == headers['Origin']
    headers['Origin'] = 'https://untrusted.example'
    response = client.options('/api/v1/workflow/chat/stream', headers=headers)
    assert 'access-control-allow-origin' not in response.headers


def test_password_update_preserves_other_settings(tmp_path, monkeypatch):
    from dotenv import dotenv_values
    path = tmp_path / '.env.cloudbase'
    url = cloudbase.connection_url('threadpilot_app', 'old-password')
    path.write_text(f"DATABASE_URL='{url}'\nOPENAI_API_KEY='keep-this-value'\n")
    monkeypatch.setattr(cloudbase, 'getpass', lambda _: 'New@Test_123456')
    cloudbase.update_password(path, 'app')
    values = dotenv_values(path, interpolate=False)
    assert make_url(values['DATABASE_URL']).password == 'New@Test_123456'
    assert values['OPENAI_API_KEY'] == 'keep-this-value'


def test_invalid_password_does_not_modify_file(tmp_path, monkeypatch):
    path = tmp_path / '.env.cloudbase'
    original = f"DATABASE_URL='{cloudbase.connection_url('threadpilot_app', 'old-password')}'\n"
    path.write_text(original)
    monkeypatch.setattr(cloudbase, 'getpass', lambda _: '\u4e2d\u6587password')
    with pytest.raises(ValueError):
        cloudbase.update_password(path, 'app')
    assert path.read_text() == original
