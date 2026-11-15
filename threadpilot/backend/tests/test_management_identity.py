from uuid import uuid4
from urllib.parse import quote
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.record_category import category


def test_conservative_categories():
    for text in ('Customer confirmed the quantity.', '已完成跟进，客户已确认。', 'No need to contact the customer.'):
        assert category('note', {'text': text}) == 'note'
    for text in ('Please confirm the delivery date tomorrow.', '明天联系客户确认交期', '待办：核对订单数量'):
        assert category('note', {'text': text}) == 'follow_up'
    assert category('note', {'text':'Please call tomorrow', 'category':'note'}) == 'note'
    assert category('briefing_watch', {'text':'anything'}) == 'follow_up'


def test_shared_attribution_classification_and_completion(business_database, monkeypatch, tmp_path):
    monkeypatch.setenv('WORKFLOW_DB', str(tmp_path/'workflow.db'))
    monkeypatch.setenv('BACKGROUND_TASKS_ENABLED', 'false')
    monkeypatch.setenv('MORNING_SCHEDULER_ENABLED', 'false')
    monkeypatch.setenv('API_ACCESS_TOKEN', 'reader')
    monkeypatch.setenv('MANAGER_ACCESS_TOKEN', 'manager')
    url='/api/v1/management-records'
    with TestClient(create_app()) as client:
        client.headers.update({'X-ThreadPilot-Token':'manager','X-ThreadPilot-Name':quote('王经理')})
        body={'request_id':str(uuid4()),'order_id':'ORD-005','text':'Please confirm the delivery date tomorrow.'}
        response=client.post(url+'/notes',json=body)
        assert response.status_code==200
        record=response.json()
        assert record['category']=='follow_up'
        assert client.post(url+'/notes',json=body).json()['id']==record['id']
        rows=client.get(url,params={'order_id':'ORD-005'}).json()['records']
        assert len(rows)==1 and rows[0]['author']=='王经理'
        assert rows[0]['category']=='follow_up'
        assert client.get(url,params={'order_id':'ORD-017'}).json()['records']==[]
        assert client.patch(url+'/'+record['id'],json={'completed':True}).status_code==200
        assert client.get(url).json()['records'][0]['status']=='completed'
        assert client.patch(url+'/'+record['id'],json={'completed':False}).status_code==200
        client.headers['X-ThreadPilot-Name']=quote('李经理')
        note=client.post(url+'/notes',json={**body,'request_id':str(uuid4()),'text':'Customer confirmed the quantity.'}).json()
        assert note['category']=='note'
        assert client.patch(url+'/'+note['id'],json={'completed':True}).status_code==404
        client.headers['X-ThreadPilot-Token']='reader'
        assert client.post(url+'/notes',json={**body,'request_id':str(uuid4())}).status_code==403
        assert client.patch(url+'/'+record['id'],json={'completed':True}).status_code==403
        client.headers['X-ThreadPilot-Token']='wrong'
        assert client.get(url).status_code==401
        client.headers['X-ThreadPilot-Token']='manager'
        assert client.delete(url+'/'+record['id']).status_code==200
        assert all(r['id']!=record['id'] for r in client.get(url).json()['records'])
