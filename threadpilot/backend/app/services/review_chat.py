"""One new intent; existing order and execution routes remain intact."""
import re
from ..schemas import Intent, ToolCall
from .review_drafts import ReviewDraftService


def review_reason_handler(app):
    async def handle(request, classification, state, now):
        engine = app.state.workflow
        service = ReviewDraftService(app.state.database)
        today = now.date().isoformat()
        ids = list(dict.fromkeys(re.findall(r'\bORD-\d{3}\b', request.message.upper())))
        def reply(answer, question=None):
            state.last_intent = Intent.REVIEW_REASON
            state.slots = classification.slots
            state.pending_clarification = None
            return engine.response(state, classification, now, answer, [], [], question)
        if len(ids) > 1 or (not ids and state.comparison_orders and not request.review_draft_id):
            return reply('请明确要为哪一张订单起草审核理由。', '请提供订单编号。')
        did = request.review_draft_id or state.review_draft_id
        draft = service.get(did, today) if did else None
        oid = ids[0] if ids else draft['order_id'] if draft else state.active_order
        if not oid:
            return reply('请提供订单编号，我会根据插队分析起草审核理由。', '请提供订单编号。')
        new = draft is None or draft['order_id'] != oid or draft['status'] != 'open'
        if new:
            draft = service.open(oid, today)
        state.review_draft_id = draft['id']
        state.active_order = oid
        state.comparison_orders = []
        state.last_order_ids = [oid]
        choice = classification.slots.review_decision
        if new and not choice and not request.review_draft_id:
            return reply('你希望批准插队、不批准插队，还是暂缓决定并保存建议？', '请选择决策倾向。')
        if choice and choice != draft['decision']:
            draft = service.change(draft['id'], draft['version'], today, decision=choice)
        if draft['stale']:
            return reply('分析已过期或数据有变化。草稿已保留，请打开审核表单，点击“重新分析”，核对影响后继续。')
        if classification.slots.action == 'adopt' and draft['text'].strip() and draft['candidate'] != draft['text']:
            result = reply('表单中已有文字。为保护你的手动编辑，请打开审核表单，点击采用并确认替换。尚未提交审核。')
            return result.model_copy(update={'tool_calls': [ToolCall(name='review_reason_draft', result={'draft_id': draft['id'], 'order_id': oid})]})
        if classification.slots.action == 'adopt':
            draft = service.change(draft['id'], draft['version'], today, adopt=True)
            answer = '已采用到审核表单，尚未提交审核，也未调整排程。请打开表单核对并确认提交。\n\n' + draft['text']
        else:
            settings = app.state.settings
            draft = await service.generate(draft['id'], draft['version'], today, request.message,
                                           app.state.client, settings.openai_model, settings.intent_api_style)
            answer = '审核理由候选草稿（尚未覆盖表单）：\n\n' + draft['candidate'] + '\n\n可以继续要求修改，或打开审核表单采用并确认提交。'
        result = reply(answer)
        return result.model_copy(update={'tool_calls': [ToolCall(name='review_reason_draft',
            arguments={'draft_id': draft['id']}, result={'draft_id': draft['id'], 'version': draft['version'],
            'review_id': draft['review_id'], 'order_id': oid}, idempotent=False)]})
    return handle
