"""CloudBase HTTP function entry; never run migrations during cold start."""
import os
import uvicorn


def main():
    required = ('DATABASE_URL', 'AI_DATABASE_URL', 'OPENAI_API_KEY', 'API_ACCESS_TOKEN',
                'DATA_API_TOKEN', 'SCHEDULER_TOKEN')
    for name in required:
        value = os.environ.get(name, '')
        if not value or value[:1] in ('\"', "'") or value[-1:] in ('\"', "'"):
            raise RuntimeError(f'{name} must be set without dotenv wrapper quotes')
    if len({os.environ[name] for name in ('API_ACCESS_TOKEN', 'DATA_API_TOKEN', 'SCHEDULER_TOKEN')}) != 3:
        raise RuntimeError('Application, administrator and scheduler tokens must differ')
    os.environ.update(WORKFLOW_STORAGE='database', BACKGROUND_TASKS_ENABLED='false',
                      SYNC_ENABLED='false', SERVE_FRONTEND='false', RAW_DATA_DIR='/tmp/threadpilot/raw')
    uvicorn.run('app.main:app', host='0.0.0.0', port=9000, workers=1, access_log=False)


if __name__ == '__main__':
    main()
