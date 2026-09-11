import json
import httpx
import pytest
from .test_api import client, provider


def upstream(answer, incomplete=False):
    text=json.dumps(answer, ensure_ascii=True)
    message={'id':'msg_1','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':text,'annotations':[]}]}
    response={'id':'resp_1','object':'response','created_at':1,'status':'completed','model':'gpt-4.1','output':[message],'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20}}
    events=[{'type':'response.created','response':{**response,'output':[],'status':'in_progress'}}, {'type':'response.output_item.added','output_index':0,'item':{**message,'content':[],'status':'in_progress'}}, {'type':'response.content_part.added','output_index':0,'content_index':0,'item_id':'msg_1','part':{'type':'output_text','text':'','annotations':[]}}]
    events += [{'type':'response.output_text.delta','output_index':0,'content_index':0,'item_id':'msg_1','delta':c} for c in text]
    if not incomplete:
        events += [{'type':'response.output_text.done','output_index':0,'content_index':0,'item_id':'msg_1','text':text}, {'type':'response.output_item.done','output_index':0,'item':message}, {'type':'response.completed','response':response}]
    return ''.join('data: '+json.dumps({**e,'sequence_number':i})+'\n\n' for i,e in enumerate(events))


def decode(response):
    frames=[]
    for frame in response.text.strip().split('\n\n'):
        lines=frame.splitlines()
        frames.append((lines[0].removeprefix('event: '),json.loads(lines[1].removeprefix('data: '))))
    return frames


def test_stream_sdk_unicode_and_metadata(client):
    answer={'answer':'Hello\n“世界” \\ 👋','order_ids':['ORD-020'],'selected_order_id':'ORD-020','sources':['orders.csv']}
    def handler(req):
        assert json.loads(req.content)['stream'] is True
        return httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=upstream(answer))
    provider(client,handler)
    response=client.post('/api/v1/chat/stream',json={'message':'Explain'})
    assert response.status_code==200
    frames=decode(response)
    assert frames[0][0]=='start' and frames[-1][0]=='done'
    assert ''.join(d['text'] for t,d in frames if t=='delta')==answer['answer']
    assert frames[-1][1]['selected_order_id']=='ORD-020'
    assert sum(t=='delta' for t,_ in frames)>2


def test_stream_missing_key(client):
    assert client.post('/api/v1/chat/stream',json={'message':'Hi'}).status_code==503


@pytest.mark.parametrize('bad_ref,incomplete',[(True,False),(False,True)])
def test_stream_failure_has_no_done(client,bad_ref,incomplete):
    answer={'answer':'Partial answer','order_ids':['ORD-999'] if bad_ref else [],'selected_order_id':None,'sources':[]}
    provider(client,lambda _:httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=upstream(answer,incomplete)))
    frames=decode(client.post('/api/v1/chat/stream',json={'message':'Hi'}))
    assert frames[-1][0]=='error'
    assert not any(t=='done' for t,_ in frames)


def test_stream_upstream_error_redacted(client):
    provider(client,lambda _:httpx.Response(429,json={'error':{'message':'PRIVATE_DETAIL'}}))
    r=client.post('/api/v1/chat/stream',json={'message':'Hi'})
    assert decode(r)[-1][1]['code']=='MODEL_RATE_LIMITED'
    assert 'PRIVATE_DETAIL' not in r.text


@pytest.mark.parametrize('typed', [False, True])
def test_quota_error_inside_http_200_stream(client, typed):
    error = {'code':'insufficient_quota','message':'You have no credits remaining.'}
    if typed:
        created = upstream({'answer':'','order_ids':[],'selected_order_id':None,'sources':[]}).split('\n\n')[0] + '\n\n'
        body = created + 'data: ' + json.dumps({'type':'error', **error, 'param':None, 'sequence_number':1}) + '\n\n'
    else:
        body = 'data: ' + json.dumps({'error': error}) + '\n\n'
    provider(client,lambda _:httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=body))
    r=client.post('/api/v1/chat/stream',json={'message':'Hi'})
    assert decode(r)[-1][1]['code']=='MODEL_QUOTA_EXCEEDED'
