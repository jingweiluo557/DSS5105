import asyncio
import json
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.review_drafts import ReviewDraftService, DraftConflict
from app.services.scheduling_service import SchedulingService, current_snapshot
from app.schemas import Classification, Intent, Slots

TODAY = '2026-04-01'


def model(text='暂不调整排程，先确认生产进度，核对受影响订单后再评估。', callback=None):
    async def create(**kwargs):
        if callback:
            callback(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps({'text': text})))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def generate(service, draft, instruction='起草理由', client=None):
    return asyncio.run(service.generate(draft['id'], draft['version'], TODAY,
                       instruction, client or model(), 'test', 'chat_completions'))


def test_continuous_revision_keeps_manual_text_and_restores(business_database):
    s = ReviewDraftService(business_database)
    d = s.open('ORD-114', TODAY)
    d = s.change(d['id'], d['version'], TODAY, text='经理手动输入', reviewer='Manager', decision='reject')
    d = generate(s, d)
    assert d['text'] == '经理手动输入'
    assert 'ORD-114' in d['candidate']
    first = d['candidate']
    seen = []
    d = generate(s, d, '再短一点', model('暂不插队，先确认生产进度。', lambda args: seen.append(args)))
    assert first == json.loads(seen[0]['messages'][1]['content'])['candidate']
    assert len(d['history']) == 4
    assert d['text'] == '经理手动输入'
    assert s.open('ORD-114', TODAY)['id'] == d['id']
    assert ReviewDraftService(business_database).get(d['id'], TODAY)['candidate'] == d['candidate']
    d = s.change(d['id'], d['version'], TODAY, adopt=True)
    assert d['text'].startswith('暂不插队') and not d['candidate']
    assert not current_snapshot(business_database, TODAY)['schedule']['priority']


def test_generation_cannot_overwrite_concurrent_edit(business_database):
    s = ReviewDraftService(business_database)
    d = s.open('ORD-114', TODAY)
    def edit(_):
        s.change(d['id'], d['version'], TODAY, text='并发手动修改')
    with pytest.raises(DraftConflict):
        generate(s, d, client=model(callback=edit))
    assert s.get(d['id'], TODAY)['text'] == '并发手动修改'
    with pytest.raises(DraftConflict):
        s.change(d['id'], d['version'], TODAY, text='旧窗口')


def test_stale_analysis_refresh_preserves_form_and_rejects_bad_model_numbers(business_database):
    s = ReviewDraftService(business_database)
    d = s.open('ORD-114', TODAY)
    d = s.change(d['id'], d['version'], TODAY, text='保留我的理由')
    with pytest.raises(ValueError, match='unverified numbers'):
        generate(s, d, client=model('可节约999天。'))
    assert s.get(d['id'], TODAY)['text'] == '保留我的理由'
    assert s.get(d['id'], '2026-04-02')['stale']
    with pytest.raises(DraftConflict):
        s.change(d['id'], d['version'], '2026-04-02', candidate='旧草稿')
    refreshed = s.change(d['id'], d['version'], '2026-04-02', refresh=True)
    assert refreshed['review_id'] != d['review_id']
    assert refreshed['text'] == '保留我的理由' and not refreshed['stale']


def test_final_decision_binds_exact_draft_version(business_database):
    s = ReviewDraftService(business_database)
    d = s.open('ORD-114', TODAY)
    d = s.change(d['id'], d['version'], TODAY, text='Reviewed', reviewer='Manager', decision='apply')
    service = SchedulingService(business_database)
    with pytest.raises(ValueError, match='draft ID'):
        service.decide(d['review_id'], 'apply', 'Manager', 'Reviewed', TODAY)
    with pytest.raises(ValueError, match='version'):
        service.decide(d['review_id'], 'apply', 'Manager', 'Reviewed', TODAY, d['id'], d['version']-1)
    with pytest.raises(ValueError, match='match'):
        service.decide(d['review_id'], 'reject', 'Manager', 'Reviewed', TODAY, d['id'], d['version'])
    assert not current_snapshot(business_database, TODAY)['schedule']['priority']
    assert service.decide(d['review_id'], 'apply', 'Manager', 'Reviewed', TODAY, d['id'], d['version'])['status'] == 'applied'
    assert s.get(d['id'], TODAY)['status'] == 'submitted'
    assert service.decide(d['review_id'], 'apply', 'Manager', 'Reviewed', TODAY, d['id'], d['version'])['replayed']
    with pytest.raises(DraftConflict):
        s.change(d['id'], d['version'], TODAY, text='Cannot change final')


def test_http_chat_draft_revise_adopt_never_executes(business_database, monkeypatch, tmp_path):
    for key,value in {'OPENAI_API_KEY':'','API_ACCESS_TOKEN':'','BACKGROUND_TASKS_ENABLED':'false',
                      'BUSINESS_NOW':TODAY+'T09:00:00+08:00', 'INTENT_API_STYLE':'chat_completions',
                      'WORKFLOW_DB':str(tmp_path/'workflow.db')}.items():
        monkeypatch.setenv(key,value)
    class Classifier:
        async def classify(self, message, state, now):
            return Classification(intent=Intent.REVIEW_REASON, confidence=1,
                slots=Slots(review_decision='reject' if '不批准' in message else None,
                            action='adopt' if '采用' in message else 'revise'))
    with TestClient(create_app()) as client:
        fake = model()
        async def close(): pass
        fake.close = close
        client.app.state.client = fake
        client.app.state.intent_classifier = Classifier()
        a = client.post('/chat',json={'message':'ORD-114 不批准插队，起草审核理由'}).json()
        assert a['intent']=='review.reason' and a['state']['review_draft_id']
        did = a['state']['review_draft_id']
        b = client.post('/chat',json={'message':'再短一点','session_id':a['state']['session_id']}).json()
        assert b['state']['review_draft_id']==did
        c = client.post('/chat',json={'message':'采用这一版','session_id':a['state']['session_id']}).json()
        assert '尚未提交' in c['answer']
        d = client.get('/api/scheduling/drafts/'+did).json()
        assert d['text'] and not d['candidate']
        assert not current_snapshot(business_database,TODAY)['schedule']['priority']
        url='/api/scheduling/reviews/'+d['review_id']+'/decision'
        assert client.post(url,json={'decision':'reject','reviewed_by':'M','note':d['text']}).status_code==409
        assert client.patch('/api/scheduling/drafts/'+did,json={'version':1,'text':'stale'}).status_code==409
        assert client.get('/api/scheduling/drafts/'+did).json()['text']==d['text']


def test_failed_model_preserves_candidate_and_manual_form(business_database):
    s = ReviewDraftService(business_database)
    d = generate(s, s.open('ORD-114', TODAY))
    d = s.change(d['id'], d['version'], TODAY, text='Keep this manual revision')
    async def fail(**kwargs):
        raise RuntimeError('Model unavailable')
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
    with pytest.raises(RuntimeError):
        generate(s, d, client=client)
    after = s.get(d['id'], TODAY)
    assert after['version']==d['version']
    assert after['candidate']==d['candidate'] and after['text']==d['text']
