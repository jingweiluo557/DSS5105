"""Chase drafts are persisted separately; only an explicit preview can be sent."""
import os
import re
from ..schemas import Classification, Intent, Slots, PendingAction, ToolCall


async def chase_chat(engine, message, result, state, now, agent, emit=None):
    explicit = list(dict.fromkeys(re.findall(r'\bORD-\d{3}\b', message.upper())))
    lower = message.casefold()
    prior = state.chase_context
    slots = result.slots
    from ..workflow_tools import resolve_datetime
    time_text = lower.replace('两分钟','2分钟').replace('二分钟','2分钟').replace('一分钟','1分钟').replace('in two minutes','in 2 minutes').replace('in one minute','in 1 minute')
    timing = re.search(r'(?:in\s+)(\d+)\s*(minutes?|hours?|seconds?)\b|(\d+)\s*(分钟|小时|秒)后',time_text)
    requested_time = slots.send_at or (timing[0] if timing and slots.action == 'send' else None)
    if requested_time:
        prior = {**prior, 'send_at':requested_time}
    mode = None
    if any(word in lower for word in ('summary', 'combined', 'consolidated', 'all-in-one', 'all together', 'one draft for', '汇总', '合并起草')):
        mode = 'summary'
    elif any(word in lower for word in ('separate', 'individually', '分别')):
        mode = 'separate'
    fresh = bool(explicit and slots.action not in ('send', 'revise')) or 'based on these recommendations' in lower or 'for this action' in lower
    # A new chase request follows the resolved current order, not an older draft topic.
    switched = (state.last_intent != Intent.EXECUTION_CHASE and state.active_order
                and slots.action not in ('send', 'revise') and not slots.draft_number and not explicit)
    if switched:
        explicit = [state.active_order]
        fresh = True
    if fresh:
        state.chase_drafts = []
    context = {} if fresh else dict(prior)
    if slots.department: context['department'] = slots.department
    if requested_time: context['send_at'] = requested_time
    ids = explicit or context.get('order_ids', [])
    if not ids and not fresh and not mode and not context and state.active_order:
        ids = [state.active_order]
    mode = mode or context.get('mode')
    mail_settings = None
    clock_run_id = None
    if getattr(engine,'email_scheduler',None) and not engine.email_scheduler.outlook.missing():
        from .email_settings import EmailSettings
        from ..business_clock import BusinessClock
        mail_settings = EmailSettings(engine.email_scheduler.outlook.settings).read()
        clock_run_id = (BusinessClock(engine.email_scheduler.outlook.settings).read() or {}).get('run_id', '')
    def destination(group):
        department = context.get('department') or (engine.tools.refresh_order(group[0]).record.get('current_stage') if len(group)==1 else None)
        return department, (mail_settings or {}).get('departments',{}).get(department)
    recipient = slots.recipient or (context.get('recipient') if mode == context.get('mode') or not mode else None)
    if slots.department and not slots.recipient:
        recipient = (mail_settings or {}).get('departments',{}).get(slots.department)
    if not recipient and len(ids)==1 and mode!='summary' and mail_settings:
        _, recipient = destination(ids)
    if mode == 'summary' and not recipient:
        recipient = 'self'
    if recipient and recipient.casefold() in ('me', 'myself', 'self', '我', '我自己'):
        recipient = (mail_settings or {}).get('manager_email') or os.getenv('CHASE_SELF_RECIPIENT', '').strip() or 'self'
    context.update(order_ids=ids, mode=mode, recipient=recipient)
    if fresh or not context.get('request'):
        context['request'] = message
    state.chase_context = context
    state.last_intent = Intent.EXECUTION_CHASE
    state.slots = slots.model_copy(update={'order_ids': ids, 'chase_mode': mode, 'recipient': recipient})
    state.last_order_ids = ids
    state.active_order = ids[0] if len(ids) == 1 else None
    state.comparison_orders = []
    state.pending_action = None
    state.pending_clarification = None
    rows = [engine.tools.refresh_order(oid) for oid in ids]
    state.active_customer = rows[0].record.get('customer') if len(rows) == 1 else None
    calls = []

    async def reply(text, question=False):
        response = (engine.ask(text, state, result, now, calls, rows, ids) if question else
                    engine.response(state, result, now, text, calls, rows))
        if emit:
            await emit(text)
        return response

    # Resolve once at the turn that supplies the time; later reviews must not move it.
    for key, supplied in (('send_at', requested_time), ('deadline', slots.deadline)):
        if supplied:
            previous = resolve_datetime(context[key], now) if context.get(key) and key == 'deadline' else None
            resolved = resolve_datetime(supplied, now, previous)
            if resolved is None or resolved <= now:
                context.pop(key, None)
                return await reply('Choose an exact future business date and time for ' + ('sending' if key == 'send_at' else 'the reply deadline') + '.', True)
            context[key] = resolved.isoformat()
    state.slots.send_at = context.get('send_at')
    state.slots.deadline = context.get('deadline')

    if slots.action == 'send':
        drafts = state.chase_drafts
        number = slots.draft_number or context.get('selected_draft')
        match = re.search(r'(?:draft\s*|第\s*)(\d+)', lower)
        if match:
            number = int(match[1])
        matches = [d for d in drafts if not d.get('sent') and (not explicit or d['order_ids'] == explicit)]
        chosen = drafts[number-1] if number and number <= len(drafts) else matches[0] if not number and len(matches) == 1 else None
        if chosen is None or chosen.get('sent'):
            return await reply('Which draft should I preview? Choose a draft number. Each draft is confirmed separately.', True)
        if 'clock_run_id' in chosen and chosen['clock_run_id'] != clock_run_id:
            return await reply('Business clock changed. Regenerate the draft before reviewing it.', True)
        if slots.department:
            chosen['department'] = slots.department
            chosen['recipient'] = recipient
        if slots.recipient:
            chosen['recipient'] = recipient
        recipient = chosen.get('recipient')
        if not recipient and chosen.get('department'):
            recipient=(mail_settings or {}).get('departments',{}).get(chosen['department'])
            chosen['recipient']=recipient
        if not recipient or recipient == 'self':
            context['selected_draft'] = drafts.index(chosen) + 1
            return await reply('What email address should I use for this draft?' if recipient == 'self' else 'Set the department email in Settings or provide the recipient email address for this draft.', True)
        context.pop('selected_draft', None)
        selected_ids = chosen['order_ids']
        if chosen.get('source_snapshots') and any(engine.tools.refresh_order(oid).record!=snapshot for oid,snapshot in chosen['source_snapshots'].items()):
            return await reply('Order data changed since this draft was generated. Regenerate the draft before reviewing it.',True)
        state.last_order_ids = selected_ids
        state.active_order = selected_ids[0] if len(selected_ids) == 1 else None
        subject = chosen.get('subject') or 'ThreadPilot chase-up | '+', '.join(selected_ids)
        preview = f"To: {recipient}\nDepartment: {chosen.get('department') or 'Specified recipient'}\nSubject: {subject}\n\n{chosen['text']}\n\nReview the recipient and text, then confirm to send this email."
        send_at = None
        if context.get('send_at'):
            send_at = resolve_datetime(context['send_at'],now)
            if send_at is None or send_at <= now:
                return await reply('Choose a future send time, for example in 2 minutes.',True)
            preview = f"To: {recipient}\nSubject: {subject}\nSend at: {send_at.isoformat()} (business time)\n\n{chosen['text']}\n\nConfirm to schedule this email."
        state.pending_action = PendingAction(kind='send', order_id=selected_ids[0] if selected_ids else '',
            payload={'recipient':recipient, 'text':chosen['text'], 'subject':subject,'department':chosen.get('department'), 'order_ids':selected_ids, 'reply_deadline':chosen.get('reply_deadline'), **({'send_at':send_at.isoformat()} if send_at else {})}, preview=preview,
            created_at=now, source_snapshots={i:engine.tools.refresh_order(i).record for i in selected_ids})
        if getattr(engine,'email_scheduler',None):
            from ..business_clock import BusinessClock
            state.pending_action.payload['clock_run_id'] = (BusinessClock(engine.email_scheduler.outlook.settings).read() or {}).get('run_id','')
        return await reply(preview)

    if context.get('selected_draft') and slots.recipient and not fresh:
        index = context.pop('selected_draft')
        state.chase_drafts[index-1]['recipient'] = recipient
        return await chase_chat(engine, f'Preview draft {index}', Classification(intent=Intent.EXECUTION_CHASE,
            confidence=1, slots=Slots(action='send', draft_number=index, recipient=recipient)), state, now, agent, emit)
    if len(ids) > 1 and not mode:
        return await reply('Orders: ' + ', '.join(ids) + '.\nWould you like one summary draft or separate drafts?', True)
    if not ids and mode != 'summary':
        return await reply('Which order should I draft for? Please give its ID, or choose a summary draft.', True)
    if len(ids) == 1 and mode != 'summary' and not recipient and mail_settings is None:
        return await reply('Who should receive the draft for ' + ids[0] + '?', True)

    selected = slots.draft_number
    if slots.action == 'revise' and selected and selected > len(state.chase_drafts):
        return await reply('Choose an existing draft number to revise.', True)
    if slots.action == 'revise' and selected and not slots.recipient and not slots.department:
        recipient = state.chase_drafts[selected-1].get('recipient')
    groups = ([state.chase_drafts[selected-1]['order_ids']] if slots.action == 'revise' and selected
              else [ids] if mode != 'separate' else [[oid] for oid in ids])
    generated = []
    answer_parts = []
    for index, group in enumerate(groups, 1):
        department, department_email = destination(group)
        group_recipient = recipient or department_email
        subject = 'ThreadPilot chase-up | '+(', '.join(group) or 'Manager summary')
        heading = f"Draft {selected if slots.action == 'revise' and selected else index} · To: {'Me' if group_recipient == 'self' else group_recipient or 'Not set'}\nDepartment: {department or 'Specified recipient'}\nSubject: {subject}\n"
        answer_parts.append(heading)
        if emit:
            await emit(heading)
        facts = [r.record for r in rows if r.record['order_id'] in group]
        previous = next((d['text'] for d in state.chase_drafts if d['order_ids'] == group), None) if slots.action == 'revise' else None
        fallback = 'Please check the current status and confirm the next steps' + (' for ' + ', '.join(group) if group else '') + '. Thank you.'
        deadline = context.get('deadline')
        revision = message
        if slots.deadline and deadline:
            revision = revision.replace(slots.deadline, deadline)
        text = await agent.compose_chase(context['request'], revision, facts, group, previous, fallback, emit,
            summary=mode == 'summary', business_now=now.isoformat(), reply_deadline=deadline)
        if deadline:
            suffix = '\n\nPlease reply by ' + deadline + ' (business time).'
            text += suffix
            if emit: await emit(suffix)
        generated.append({'order_ids':group,'recipient':group_recipient,'department':department,'subject':subject,'text':text,'sent':False,
                          'reply_deadline':deadline, 'business_now':now.isoformat(),
                          'clock_run_id':clock_run_id,
                          'source_snapshots':{r.record['order_id']:r.record for r in rows if r.record['order_id'] in group}})
        answer_parts.append(text + '\n\n')
        if emit:
            await emit('\n\n')
    if slots.action == 'revise' and selected:
        state.chase_drafts[selected-1] = generated[0]
    else:
        state.chase_drafts = generated
    footer = 'Draft only; nothing sent. Ask to send a draft by number to review and confirm it.'
    answer_parts.append(footer)
    if emit:
        await emit(footer)
    calls.append(ToolCall(name='draft_chase', result={'drafts':generated}))
    return engine.response(state, result, now, ''.join(answer_parts), calls, rows)
