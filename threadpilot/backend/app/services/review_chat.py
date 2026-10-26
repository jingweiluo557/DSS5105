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
            return reply('Which order should the review reason cover?', 'Please provide the order ID.')
        did = request.review_draft_id or state.review_draft_id
        draft = service.get(did, today) if did else None
        oid = ids[0] if ids else draft['order_id'] if draft else state.active_order
        if not oid:
            return reply('Please provide the order ID so I can draft a reason based on the expedite analysis.', 'Please provide the order ID.')
        new = draft is None or draft['order_id'] != oid or draft['status'] != 'open'
        if new:
            draft = service.open(oid, today)
        state.review_draft_id = draft['id']
        state.active_order = oid
        state.comparison_orders = []
        state.last_order_ids = [oid]
        choice = classification.slots.review_decision
        if new and not choice and not request.review_draft_id:
            return reply('Would you like to approve, reject, or defer the expedite request?', 'Please select a decision.')
        if choice and choice != draft['decision']:
            draft = service.change(draft['id'], draft['version'], today, decision=choice)
        if draft['stale']:
            return reply('The analysis has expired or the data has changed. Your draft is preserved. Open the review form and refresh the analysis before continuing.')
        if classification.slots.action == 'adopt' and draft['text'].strip() and draft['candidate'] != draft['text']:
            result = reply('The form already contains text. Open the review form to adopt this draft and confirm replacement. No review has been submitted.')
            return result.model_copy(update={'tool_calls': [ToolCall(name='review_reason_draft', result={'draft_id': draft['id'], 'order_id': oid})]})
        if classification.slots.action == 'adopt':
            draft = service.change(draft['id'], draft['version'], today, adopt=True)
            answer = 'Added to the review form. No review has been submitted and no schedule has changed. Check the form before confirming.\n\n' + draft['text']
        else:
            settings = app.state.settings
            draft = await service.generate(draft['id'], draft['version'], today, request.message,
                                           app.state.client, settings.openai_model, settings.intent_api_style)
            answer = 'Review reason draft (not yet applied to the form):\n\n' + draft['candidate'] + '\n\nYou can request revisions or open the review form to adopt and confirm.'
        result = reply(answer)
        return result.model_copy(update={'tool_calls': [ToolCall(name='review_reason_draft',
            arguments={'draft_id': draft['id']}, result={'draft_id': draft['id'], 'version': draft['version'],
            'review_id': draft['review_id'], 'order_id': oid}, idempotent=False)]})
    return handle
