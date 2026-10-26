"""Opt-in real MySQL / model smoke test. Cleans up only its own workflow rows."""
import json
import os
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.config import ROOT


def main():
    values = json.loads((ROOT / 'backend/.env.cloudfunction.json').read_text(encoding='utf-8'))
    os.environ.update(values)
    os.environ['RAW_DATA_DIR'] = str(ROOT / '.build/smoke-raw')
    os.environ['CHASE_WEBHOOK_URL'] = ''
    from app.main import create_app
    from app.sql_workflow_store import SQLWorkflowStore, WorkflowBusy, sessions, sql_sessions, actions, reminders, notifications
    from app.schemas import DialogState
    ids = []
    sql_ids = []
    with TestClient(create_app()) as client:
        engine = client.app.state.database.engine
        headers = {'X-ThreadPilot-Token': values['API_ACCESS_TOKEN']}
        store = SQLWorkflowStore(engine)
        try:
            state = DialogState()
            ids.append(state.session_id)
            store.save(state)
            assert SQLWorkflowStore(engine).load(state.session_id).revision == 0
            with store.turn_lock('smoke:' + state.session_id):
                try:
                    with SQLWorkflowStore(engine).turn_lock('smoke:' + state.session_id):
                        raise AssertionError('Concurrent lock was allowed')
                except WorkflowBusy:
                    pass
            with store.turn_lock('smoke:' + state.session_id):
                pass
            print('MySQL persistence and cross-connection lock: PASS')
            assert client.get('/api/snapshot').status_code == 401
            assert client.get('/api/snapshot', headers=headers).status_code == 200
            print('Cloud database snapshot and access control: PASS')
            result = client.post('/api/v1/workflow/chat', headers=headers,
                                 json={'message': 'Open order ORD-005 and show its current status.'})
            assert result.status_code == 200, 'Workflow status ' + str(result.status_code)
            body = result.json()
            ids.append(body['state']['session_id'])
            assert body['state']['active_order'] == 'ORD-005'
            assert SQLWorkflowStore(engine).load(ids[-1]).active_order == 'ORD-005'
            print('Real model workflow and persisted state: PASS')
            result = client.post('/api/ai/ask', headers=headers,
                                 json={'message': 'How many orders are in the database? Use COUNT(*). Do not list individual orders.'})
            assert result.status_code == 200, 'SQL Agent status ' + str(result.status_code)
            body = result.json()
            sql_ids.append(body['session_id'])
            assert body['queries']
            assert SQLWorkflowStore(engine).load_history(sql_ids[-1])
            print('Real SQL Agent and persisted history: PASS')
        finally:
            with engine.begin() as connection:
                for table in (notifications, reminders, actions):
                    connection.execute(table.delete().where(table.c.session_id.in_(ids)))
                connection.execute(sessions.delete().where(sessions.c.id.in_(ids)))
                connection.execute(sql_sessions.delete().where(sql_sessions.c.id.in_(sql_ids)))
            print('Own smoke-test workflow records cleaned up.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Third-party exceptions may contain connection details; do not print them.
        print('Smoke test failed:', type(exc).__name__)
        raise SystemExit(1)
