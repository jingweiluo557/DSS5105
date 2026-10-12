"""Create private console JSON from local CloudBase credentials; never print secrets."""
import json
import secrets
from dotenv import dotenv_values, set_key
from app.config import ROOT


def main():
    source = ROOT / 'backend/.env.cloudbase'
    values = dotenv_values(source, interpolate=False)
    for key in ('API_ACCESS_TOKEN', 'SCHEDULER_TOKEN'):
        if not values.get(key):
            values[key] = secrets.token_urlsafe(32)
            set_key(source, key, values[key])
    keys = ('DATABASE_URL', 'AI_DATABASE_URL', 'OPENAI_API_KEY', 'OPENAI_BASE_URL',
            'OPENAI_MODEL', 'INTENT_API_STYLE', 'DATA_API_TOKEN', 'API_ACCESS_TOKEN',
            'SCHEDULER_TOKEN', 'BUSINESS_NOW', 'CORS_ORIGINS')
    config = {key: values[key] for key in keys if values.get(key)}
    config.update(PORT='9000', WORKFLOW_STORAGE='database', BACKGROUND_TASKS_ENABLED='false',
                  SYNC_ENABLED='false', SERVE_FRONTEND='false', RAW_DATA_DIR='/tmp/threadpilot/raw',
                  OPENAI_TIMEOUT_SECONDS='45', SQL_AGENT_STEPS='8')
    target = ROOT / 'backend/.env.cloudfunction.json'
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    timer = {'BACKEND_ORIGIN': 'https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com',
             'SCHEDULER_TOKEN': values['SCHEDULER_TOKEN']}
    target.with_name('.env.cloudfunction-timer.json').write_text(json.dumps(timer, indent=2) + '\n', encoding='utf-8')
    print('Private backend and timer JSON configuration generated; no credentials printed.')


if __name__ == '__main__':
    main()
