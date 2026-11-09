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
    from ..workflow_engine import detect_customer
    from ..schemas import Slots as _Slots
    notes = []
    # "Chase up the TrendCart order": the customer named in the manager's words decides the candidates, never the
    # order the UI happened to have open (26 Oct question sheet, rows 42 and 47).
    customer = detect_customer(message, engine.tools) if not explicit and slots.action not in ('send', 'revise') else None
    if customer:
        matches = engine.tools.search_orders(_Slots(customer=customer))
        if len(matches) == 1:
            explicit = [matches[0].record['order_id']]
        else:
            state.active_order = None
            state.chase_context = {}
            state.last_order_ids = [e.record['order_id'] for e in matches]
            text = (f"Which {customer} order should I chase? " + '; '.join(engine.candidate_hint(e.record, now) for e in matches) + '. Give the order ID.') if matches else f'{customer} has no order in progress to chase.'
            found = [engine.candidate_call(matches, now, customer=customer)]
            response = engine.ask(text, state, result, now, found, matches, state.last_order_ids) if matches else engine.response(state, result, now, text, found, [])
            if emit: await emit(text)
            return response
    # "Chase the order with 1500 tops" / "chase orders overdue more than 2 days" / "chase all orders from the largest customer":
    # the description names the candidates; one match is taken and stated, several are listed (or all drafted when asked for all).
    pronoun = re.search(r'\b(this|that) (order|one)\b|\bthe order\b(?! (with|of|for|that|which|at|in|from))|\bit\b|\bthis\b$', lower)
    if (not explicit and not customer and not slots.department and slots.action not in ('send', 'revise') and not slots.draft_number and not mode and not pronoun
            and re.search(r'\b(with|of|for|at|in|stuck|pending|phase|stage|overdue|overdued|late|largest|biggest|main|scar|beanie|vest|hood|cardigan|polo|sweater|crewneck|tops|accessor|idle|stalled)\w*', lower)):
        described = engine.describe_candidates(message, now)
        # "The vest one" right after a candidate list narrows that list (ORD-120 of the three 1,500-piece tops orders), not
        # every vest order on file: found while recording the Sprint 3 demo.
        open_ids = list((state.pending_clarification.candidates if state.pending_clarification else []) or [])
        if described and open_ids and described[1] and len(message.split()) <= 6 and not re.search(r'\ball\b|\bevery\b|largest|biggest|overdue|late\b', lower):
            narrowed = [e for e in described[1] if e.record['order_id'] in open_ids]
            if narrowed and len(narrowed) < len(described[1]):
                product = narrowed[0].record['product'].lower()
                named = product.split()[0] in lower
                described = ((f"the {product} order among the {len(open_ids)} listed" if named else f"{narrowed[0].record['order_id']}, the one among the {len(open_ids)} listed")
                             if len(narrowed) == 1 else f"{len(narrowed)} of the {len(open_ids)} listed", narrowed)
        if described and not described[0].startswith('reading '):
            label, matches = described
            found = [engine.candidate_call(matches, now, description=label)]
            if not matches:
                response = engine.response(state, result, now, label[0].upper() + label[1:] + '.', found, [])
                if emit: await emit(response.answer)
                return response
            if len(matches) == 1 or (re.search(r'\ball\b', lower) and len(matches) <= 10):
                explicit = [e.record['order_id'] for e in matches]
                notes.append(f'(Reading "{message.strip()}" as {label}: ' + ', '.join(explicit) + '.)')
                if len(explicit) > 1 and not mode:
                    mode = 'separate'
            else:
                state.active_order = None
                state.chase_context = {}
                state.last_order_ids = [e.record['order_id'] for e in matches]
                text = f'Which one should I chase? {label}: ' + '; '.join(engine.candidate_hint(e.record, now) for e in matches) + '. Give the order ID, or say "all of them" for one draft per order.'
                response = engine.ask(text, state, result, now, found, matches, state.last_order_ids)
                if emit: await emit(text)
                return response
    # A claim that the order is finished is checked against the record before anything is drafted ("since ORD-005 has
    # already shipped", "order 5 is done and delivered, right?"), and the customer is never a recipient: the chat writes to
    # departments and workshops only; customer contact is a stated non-goal.
    target_ids = explicit or ([state.active_order] if state.active_order else [])
    if len(target_ids) == 1 and re.search(r'\b(already )?(shipped|delivered|dispatched|done and delivered|is done|completed|complete)\b', lower) and slots.action not in ('send', 'revise'):
        rec = engine.tools.refresh_order(target_ids[0]).record
        if rec['status'] == 'IN_PROGRESS':
            text = (f"{target_ids[0]} has not shipped: the record shows it in progress at {rec['current_stage'].lower()}, due {rec['due_date']}, last recorded activity {rec['last_activity_date']}. "
                    + ('I also do not write to customers: chase-ups go to our departments and workshops. ' if re.search(r'\bcustomer|client\b', lower) else '')
                    + f"Do you want a chase-up to the {rec['current_stage'].lower()} team instead?")
            response = engine.ask(text, state, result, now, [ToolCall(name='refresh_order', arguments={'order_id': target_ids[0]}, result={'status': rec['status'], 'current_stage': rec['current_stage'], 'premise': 'not shipped'})], [engine.tools.refresh_order(target_ids[0])])
            if emit: await emit(text)
            return response
    if (slots.recipient and re.search(r'^(the )?(customer|client|buyer)s?$', slots.recipient.strip(), re.I)) or re.search(r'\b(write|draft|send|email|chase|message)\b[^.]{0,40}\bto the customer\b|\bcustomer a (follow-up|note|message|update|reply)\b|\btell the customer\b|\bpromise the customer\b|\bcustomer-facing\b|\bchase (the )?customer\b|\bemail the customer\b', lower):
        text = ('I do not write to customers: chase-ups go to our departments and outside workshops, and delivery promises are the manager\u2019s to make. '
                + (f"I can draft an internal chase-up on {target_ids[0]} asking for the expected completion date, if you want it." if target_ids else 'Name the order and I can draft an internal chase-up asking for the expected completion date.'))
        response = engine.response(state, result, now, text, [ToolCall(name='explain_no_data', arguments={'reason': 'external'}, result={'declined': True, 'reason': 'external', 'answer': text}, executed=False)], [])
        if emit: await emit(text)
        return response
    if slots.action == 'read' or re.search(r'\b(did (we|i) send|was (it|that) sent|is it still a draft|who received|what did we send|have we (sent|chased)|sent yet)\b', lower):
        sent = []
        oid = target_ids[0] if target_ids else None
        try:
            if oid: sent = engine.store.actions_for(oid, ('send',))
        except Exception:
            sent = []
        drafts = [d for d in state.chase_drafts if not oid or oid in d.get('order_ids', [])]
        if sent:
            lines = '; '.join(f"{s.get('created_at', '')[:16]} to {s.get('recipient')} ({s.get('status')})" for s in sent[:5])
            text = f"Yes: {len(sent)} chase-up{'s' if len(sent) != 1 else ''} recorded for {oid}: {lines}. The activity log has the full text."
        elif drafts:
            text = f"No chase-up for {oid or 'that order'} has been sent from this workspace. {len(drafts)} draft{'s' if len(drafts) != 1 else ''} exist{'s' if len(drafts) == 1 else ''} unsent" + (f" (to {drafts[-1].get('recipient') or 'no recipient yet'})" if drafts else '') + '; ask to preview a draft by number to send it.'
        else:
            text = f"No chase-up for {oid} has been sent or drafted from this workspace." if oid else 'Which order? No order is in focus, so I cannot check its chase-up record.'
        response = engine.response(state, result, now, text, [ToolCall(name='send_chase', arguments={'order_id': oid, 'action': 'read'}, result={'sent': sent, 'drafts': len(drafts)}, executed=False)], [])
        if emit: await emit(text)
        return response
    promise = re.search(r'\b(promise|guarantee|assure|commit to|definitely|will arrive|will be delivered)\b', lower)
    if promise and slots.action not in ('send', 'revise'):
        notes.append('I will not put a delivery promise in writing on your behalf: the draft asks the workshop for its expected completion date instead, and you decide what to tell the customer.')
        slots = slots.model_copy(update={'text': None})
        result = result.model_copy(update={'slots': slots})
    # "Draft a chase-up to packing for ORD-083 and send it": no draft exists for that order yet, so draft it and show the preview.
    if slots.action == 'send' and explicit and not any(d.get('order_ids') == explicit and not d.get('sent') for d in state.chase_drafts) and re.search(r'\b(draft|write|chase|email|ask)\b', lower) and not re.search(r'straight away|right away|immediately|no need to show|without showing|don.t show|no preview|skip the preview', lower):
        slots = slots.model_copy(update={'action': 'draft', 'draft_number': None})
        result = result.model_copy(update={'slots': slots})
        notes.append('Nothing is sent without a preview and your confirmation. Here is the draft:')
    # "Send it" / "send it straight away, no need to show me" with nothing drafted yet: the preview cannot be skipped, so draft and show it.
    if slots.action == 'send' and not any(not d.get('sent') and (d.get('order_ids') == (explicit or [state.active_order])) for d in state.chase_drafts) and (explicit or state.active_order) and not slots.draft_number:
        slots = slots.model_copy(update={'action': 'draft', 'draft_number': None})
        result = result.model_copy(update={'slots': slots})
        notes.append('Nothing is sent without a preview and your confirmation. Here is the draft:' if not re.search(r'straight away|right away|immediately|no need to show|without showing|don.t show|no preview|skip the preview', lower)
                     else 'I cannot send without showing you the draft first: every send needs a preview and your confirmation. Here is the draft:')
    fresh = bool(explicit and slots.action not in ('send', 'revise')) or 'based on these recommendations' in lower or 'for this action' in lower
    # A new chase request follows the resolved current order, not an older draft topic.
    switched = (state.last_intent != Intent.EXECUTION_CHASE and state.active_order
                and slots.action not in ('send', 'revise') and not slots.draft_number and not explicit)
    if switched:
        explicit = [state.active_order]
        fresh = True
    # A claim about idle time is checked against the record before any draft ("hasn't moved in a week" vs 2 days).
    claim = re.search(r"(?:hasn.t|has not|not) (?:moved|progressed|changed|had (?:any )?activity)[^.]*?(?:in|for) (?:over |more than |about |almost )?(a|an|\d+|one|two|three|four|five|six|seven) (week|weeks|day|days|fortnight)", lower)
    # ... and the same for "stuck at washing since last week", "idle for 10 days", "no movement since last wk" (Sprint 3 demo: ORD-029 moved today)
    stuck = None if claim else re.search(r"(?:stuck|idle|sitting|parked|stalled|no (?:movement|activity|progress|update)|not moving)[^.]*?(?:since|for) (?:the )?(?:(last) (week|wk|fortnight)|(a|an|\d+|one|two|three|four|five|six|seven|ten) (weeks?|wks?|days?|d\b|fortnight))", lower)
    if stuck:
        claim = (stuck[0], stuck[1] or stuck[3], (stuck[2] or stuck[4]).replace('wks', 'weeks').replace('wk', 'week').replace('d', 'days') if (stuck[2] or stuck[4]) in ('wk', 'wks', 'd') else (stuck[2] or stuck[4]))
    if claim and len(explicit) == 1 and slots.action not in ('send', 'revise') and not prior.get('premise_checked') == explicit[0]:
        words = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'ten': 10, 'last': 1}
        n = int(claim[1]) if claim[1].isdigit() else words[claim[1]]
        claimed = n * (7 if claim[2].startswith('week') else 14 if claim[2] == 'fortnight' else 1)
        record = engine.tools.refresh_order(explicit[0]).record
        from datetime import date as _date
        idle = (now.date() - _date.fromisoformat(record['last_activity_date'])).days
        if claimed - idle >= 2:
            due = _date.fromisoformat(record['due_date'])
            to_due = (due - now.date()).days
            when = 'today' if idle == 0 else f"{idle} day{'s' if idle != 1 else ''} ago"
            text = (f"{explicit[0]} was last active {record['last_activity_date']}, {when}, not {'since ' if claim[1] == 'last' else ''}{claim[1]} {claim[2]}. "
                    f"It is {record['customer']}, {record['pieces']} {record['product']}, at {record['current_stage'].lower()}, " +
                    (f"due in {to_due} days" if to_due > 0 else 'due today' if to_due == 0 else f"{-to_due} days overdue") +
                    ", so it is not stalled by the 5-day rule. Do you still want me to draft the chase-up?")
            state.chase_context = {'premise_checked': explicit[0], 'order_ids': explicit, 'request': message}
            state.active_order = explicit[0]
            state.last_order_ids = explicit
            state.last_intent = Intent.EXECUTION_CHASE
            response = engine.ask(text, state, result, now, [ToolCall(name='refresh_order', arguments={'order_id': explicit[0]}, result=record)], [engine.tools.refresh_order(explicit[0])], explicit)
            if emit: await emit(text)
            return response
    if prior.get('premise_checked') and not explicit and re.match(r'^\s*(yes|yes please|go ahead|draft it|please do|ok|okay|sure)\b', lower):
        explicit = [prior['premise_checked']]
        fresh = True
    if fresh:
        state.chase_drafts = []
    context = {} if fresh else dict(prior)
    if slots.department: context['department'] = slots.department
    if requested_time: context['send_at'] = requested_time
    ids = explicit or context.get('order_ids', [])
    if not ids and not fresh and not mode and state.active_order and (not context or re.search(r'\b(this order|the order|this one|this|it)\b', lower)):
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
        if notes:   # the "cannot skip the preview" rule is said first, whatever question follows it
            text = notes[0].replace('Here is the draft:', '').rstrip() + ' ' + text
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
            if resolved is not None and resolved <= now and key == 'deadline' and not re.search(r'\d{4}-\d{2}-\d{2}|today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday', supplied.lower()):
                # "reply by 11:30" said at noon: that clock time has passed today, so the next working day at that time, and say so
                from datetime import timedelta as _td
                nxt = resolved + _td(days=1)
                while nxt.weekday() == 6: nxt += _td(days=1)
                notes.append(f"{supplied} has already passed today (business time {now.strftime('%H:%M')}), so the deadline is set to {nxt.strftime('%A %d %b %H:%M')}; say another time to change it.")
                resolved = nxt
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
            if not any(not d.get('sent') for d in drafts):
                return await reply('There is no unsent draft in this chat, so nothing was sent. Say which order to draft for and I will show the preview first.', True)
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
        if slots.action == 'revise' or (not state.chase_drafts and re.search(r'\b(cc|recipient|firmer|softer|shorter|politer?|tone|deadline|reply by|add (this|that)|change the)\b', lower)):
            return await reply('There is no draft in this chat to revise, so nothing was changed or sent. Say which order to draft for and I will write it with that change included.', True)
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
        to_line = 'Me' if group_recipient == 'self' else group_recipient or ('Not set' + (f" (no email saved for {department} in Settings; name a recipient before sending)" if department else ' (name a recipient before sending)'))
        heading = f"Draft {selected if slots.action == 'revise' and selected else index} · To: {to_line}\nDepartment: {department or 'Specified recipient'}\nSubject: {subject}\n"
        answer_parts.append(heading)
        if emit:
            await emit(heading)
        facts = [r.record for r in rows if r.record['order_id'] in group]
        previous = next((d['text'] for d in state.chase_drafts if d['order_ids'] == group), None) if slots.action == 'revise' else None
        fallback = 'Please check the current status and confirm the next steps' + (' for ' + ', '.join(group) if group else '') + '. Thank you.'
        if slots.text and slots.action != 'revise':
            # no model: the manager's own question still goes into the draft, so the degraded draft is not an empty chase
            ask = slots.text.strip().rstrip('.?!')
            fallback = 'Please check the current status' + (' of ' + ', '.join(group) if group else '') + f' and let us know: {ask[0].lower() + ask[1:]}? Thank you.'
        elif slots.text and previous:
            fallback = previous.rstrip() + '\n' + slots.text.strip().rstrip('.') + '.'
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
    if notes:
        answer_parts.insert(0, notes[0] + '\n')
    if emit:
        await emit(footer)
    calls.append(ToolCall(name='draft_chase', result={'drafts':generated}))
    return engine.response(state, result, now, ''.join(answer_parts), calls, rows)
