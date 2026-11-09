"""场景 1.1–3.3：模型识别、确定性路由、状态与确认闸门。"""
import asyncio
import json
import re
from time import perf_counter
from contextlib import nullcontext
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Protocol

from .services.order_record_intent import preview as record_preview, propose_watch
from .schemas import (ChatRequest, ChatResponse, Classification, DialogState, Evidence,
                      Intent, PendingAction, PendingClarification, Slots, ToolCall)
from .workflow_store import Sender, WorkflowStore
from .workflow_tools import DataTools, resolve_date, resolve_datetime, resolve_period, parse_day


class Classifier(Protocol):
    async def classify(self, message: str, state: DialogState, now: datetime) -> Classification:
        """场景 1.1–3.3：允许真实 SDK 与测试替身使用同一分类接口。"""
        ...


# Sprint 2: explicit refusals. The brief scores "this system holds no price data" above a non-answer, so an
# unknown or low-confidence request is matched against the dataset's stated non-goals before we ask a question.
NON_GOALS: dict[str, tuple[tuple[str, ...], str]] = {
    'money': (('revenue', 'price', 'pricing', 'cost', 'margin', 'profit', 'invoice', 'penalty', 'sales value', 'turnover', 'budget', '收入', '价格', '成本', '利润'),
              'This system holds no prices, costs, revenue or margins: orders.csv records who ordered what, how many pieces and when. '
              'I can report counts, pieces, due dates, stages and delays for any customer or order instead.'),
    'people': (('worker', 'operator', 'employee', 'staff member', 'who was responsible', 'who is responsible', 'whose fault', 'shift leader', 'technician', '工人', '员工', '谁负责'),
               'The data has no worker, operator or shift records: production_log.csv holds factory-wide pieces per stage per day only. '
               'I can show the stage output and compare it with the same weekday, but not who was on the line.'),
    'cause': (('root cause', 'why did the machine', 'machine break', 'breakdown', 'downtime', 'what caused'),
              'The production log records output, not downtime, blockers or causes. I can show how far a day fell outside its same-weekday range '
              'and which records co-occurred, but any cause has to come from the floor.'),
    'delete': (('delete', 'remove the order', 'erase', 'drop the order', 'wipe', '删除'),
               'I cannot delete or modify orders: the chat reads the order records and can only draft a chase-up, save an internal note or set a reminder, '
               'each after your confirmation. Nothing was changed.'),
    'cancel': (('cancel the order', 'cancel order', 'cancel ord', 'void the order', 'terminate the order', '取消订单'),
               'I cannot cancel orders or contact customers: order changes are made in the factory system, and the chat only drafts internal '
               'chase-ups, notes and reminders after confirmation. Nothing was changed or sent.'),
    'history': (('what changed since', 'changed since yesterday', 'since yesterday\u2019s', "since yesterday's", 'newly emerged', 'resolved, worsened', 'resolved or worsened', 'compared with yesterday\u2019s list', "compared with yesterday's list"),
                'The system keeps no dated exception snapshots, so it cannot say what changed since yesterday. The archived 07:00 briefings hold each day\u2019s counts '
                'and advice (Dashboard \u2192 Morning briefing); today\u2019s list comes from "what needs attention today". A missing item is not evidence that it was resolved.'),
    'external': (('email the customer', 'call the customer', 'tell the customer', 'notify the customer', 'message the customer', 'whatsapp'),
                 'Customer-facing messages are outside this co-pilot: it drafts internal chase-ups to the planner or a department, and sends only after you confirm. '
                 'I can draft the internal message or the facts you would tell the customer.'),
}


def refusal(message: str) -> tuple[str, str] | None:
    """Return (reason, answer) when the request asks for something the dataset or the tool set deliberately does not hold."""
    lowered = message.casefold()
    for reason, (keywords, answer) in NON_GOALS.items():
        if any(k in lowered for k in keywords):
            return reason, answer
    return None


STAGE_ORDER = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']
STAGE_WORDS = {'knitting': 'KNITTING', 'knit': 'KNITTING', 'assembly': 'ASSEMBLY', 'linking': 'ASSEMBLY', 'washing': 'WASHING', 'wash': 'WASHING', 'packing': 'PACKING', 'pack': 'PACKING'}
DATE_QUESTION = 'Which date should I check? For example "yesterday", "31 March" or "2026-03-31".'
STAGE_QUESTION = 'Which stage: knitting, assembly, washing or packing? Say "all four" to compare every stage.'


def known_customers(tools: DataTools) -> list[str]:
    return sorted({e.record['customer'] for e in tools.rows('orders.csv')})


def detect_customer(message: str, tools: DataTools) -> str | None:
    """A customer named in the manager's own words (never from planner prose)."""
    lowered = message.casefold()
    hits = [c for c in known_customers(tools) if c.casefold() in lowered or c.casefold().replace(' & ', ' and ') in lowered]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        # "Trend Cart", "trendcart", "cotonclub": compare on letters only, allowing one or two typos
        import difflib
        compact = re.sub(r'[^a-z0-9]', '', lowered)
        for c in known_customers(tools):
            key = re.sub(r'[^a-z0-9]', '', c.casefold())
            for i in range(0, max(1, len(compact) - len(key) + 3)):
                window = compact[i:i + len(key)]
                if window and difflib.SequenceMatcher(None, window, key).ratio() >= 0.88:
                    hits.append(c); break
    return hits[0] if len(set(hits)) == 1 else None


def detect_workshop(message: str, tools: DataTools) -> dict | None:
    lowered = message.casefold()
    for e in tools.rows('workshops.csv'):
        r = e.record
        if r['name'].casefold() in lowered or r['workshop_id'].casefold() in re.findall(r'\bw\d\b', lowered):
            return r
    return None


def stages_in(message: str) -> list[str]:
    lowered = message.casefold()
    found = list(dict.fromkeys(code for word, code in STAGE_WORDS.items() if re.search(r'\b' + word + r'\b', lowered)))
    # a one-letter slip in a stage name ("knittng", "assembely", "pakcing") still names the stage
    import difflib
    for token in re.findall(r'[a-z]{6,}', lowered):
        for word, code in STAGE_WORDS.items():
            if len(word) >= 6 and code not in found and difflib.SequenceMatcher(None, token, word).ratio() >= 0.85:
                found.append(code)
    return found


def article(word: str) -> str:
    return 'an' if word[:1].lower() in 'aeiou' else 'a'


def comparative_stage_question(message: str) -> bool:
    """'Which stage is most off', 'all four stages', 'each stage', 'why was output lower' (no stage named).
    'Why was packing output lower yesterday?' names a stage, so it is not comparative."""
    lowered = message.casefold()
    if re.search(r'which stage|what stage|most (off|unusual|concerning|behind|worrying)|worry about most|all (four |4 )?stages|every stage|each stage|across (the )?stages|total output|factory.s (total )?output|overall output', lowered):
        return True
    return bool(re.search(r'output (was )?lower|output (was|were) (down|low)\b', lowered)) and not stages_in(message)


def mentions_order_reference(message: str) -> bool:
    """Does the message point at an order at all (an ID, a customer, a product, 'it', 'that order')?"""
    lowered = message.casefold()
    return bool(re.search(r'\bord-\d{3}\b|\b(it|its|that order|this order|the order|that one|the first|the second|the scarf|the beanie|the vest|the hoodie|the cardigan|the polo|the sweater)\b', lowered))


def hypothetical_policy(message: str) -> str | None:
    """A decision-rule question about made-up orders ('a VIP customer order', 'two orders need the same machines',
    'an order is due tomorrow but packed; another ...'): answer the rule, say what the data can and cannot check,
    and offer to run it on real IDs. Never pick an order for it."""
    lowered = message.casefold()
    hypothetical = re.search(r'\b(a|an|another|two|one) (vip |regular |customer |urgent |rush )?(customer )?orders?\b', lowered) and not re.search(r'\bord-\d{3}\b', lowered)
    if not hypothetical:
        return None
    if 'vip' in lowered:
        return ('VIP status alone should not override an earlier firm commitment. The rule this system can apply: the earlier due date keeps priority unless '
                'the manager approves an expedite after seeing the queue impact (Risk \u2192 Analyze expedite impact shows the days saved for the VIP order and the '
                'lateness added to the regular one). The data has no customer-tier, penalty or contract fields, so weigh those outside the system. '
                'Give me the two order IDs and I will show the dates, stages, idle days and the expedite trade-off for both.')
    if re.search(r'machine|gauge|knitting', lowered):
        return ('The data does not record machines, gauges, standard minutes or yarn, so I cannot pick a sequence from machine compatibility. What it can do: '
                'compare the two orders\u2019 due dates, stages and idle days, and run the expedite analysis, which shows how many working days the first order '
                'gains and how late the other becomes if one goes ahead in each stage queue. Give me the two order IDs and I will run it.')
    if re.search(r'packed|yarn|material|dispatch', lowered):
        return ('Deadline alone does not decide this. Recorded in this system: each order\u2019s stage (an order at packing is one stage from done), due date, '
                'last activity and the queue\u2019s best-case finish. Not recorded: dispatch booking, yarn or material status. The rule: an order already packed with '
                'dispatch secured is low risk even if due tomorrow; an order five days out with a missing input is the one to escalate, because the procurement '
                'lead time sits on its critical path. Give me the two order IDs and I will check their stages, dates and queue finish.')
    return ('I can only decide this on real orders: give me the order IDs and I will compare due dates, stages, idle days and the queue\u2019s best-case finish, '
            'and run the expedite trade-off. The data holds no customer tiers, penalties, machines or materials.')


class WorkflowEngine:
    def __init__(self, tools: DataTools, store: WorkflowStore, clock: Callable[[], datetime], sender: Sender | None = None) -> None:
        """场景 1.1–3.3：共享工具、持久化和显式业务时钟；串行保护本地状态。"""
        self.tools, self.store, self.clock, self.sender = tools, store, clock, sender
        self.lock = asyncio.Lock()

    async def chat(self, request: ChatRequest, classifier: Classifier, emit=None, role: str = 'manager') -> ChatResponse:
        """场景 1.1–3.3：原子处理一个本地会话轮次，客户端不能提交状态或工具。"""
        async with self.lock:
            with self.store.turn_lock('chat:' + request.session_id) if request.session_id and hasattr(self.store, 'turn_lock') else nullcontext():
                return await self._chat(request, classifier, emit, role)

    async def _chat(self, request: ChatRequest, classifier: Classifier, emit=None, role: str = 'manager') -> ChatResponse:
        state = self.store.load(request.session_id) if request.session_id else DialogState()
        now = self.clock()
        # "ORD 080", "order ID 080", "ord080" are the manager's explicit IDs too: normalise them before the explicit-ID rule,
        # the memory and the planner see the message (services/order_refs.py). The history keeps the manager's own words.
        from .services.order_refs import expand_shorthand, normalize_order_numbers, normalize_order_refs
        raw_message = request.message
        normalized = normalize_order_numbers(normalize_order_refs(expand_shorthand(request.message)), self.known_order_numbers(), self.known_products())
        if normalized != request.message:
            request = request.model_copy(update={'message': normalized})
        if request.selected_order_id and not state.active_order and not state.comparison_orders:
            # The order highlighted in the UI only stands in for "it" / "this order". A message that names a customer,
            # a product, an ID or describes an order ("the one that was late yesterday") must resolve on its own words.
            lowered = request.message.casefold()
            products = {e.record['product'].casefold() for e in self.tools.rows('orders.csv')}
            names_something = (detect_customer(request.message, self.tools) or re.search(r'\bord-\d{3}\b', lowered)
                               or any(p in lowered or p.rstrip('s') in lowered for p in products)
                               or re.search(r'\b(late|overdue|stalled|idle|which|orders)\b', lowered))
            if not names_something:
                state.active_order = self.tools.refresh_order(request.selected_order_id).record['order_id']
        confirmed = self.confirmation_word(request.message)
        original_message, memory_notes = raw_message, []
        if not confirmed:
            # Several orders in one chat: "the first one", "the other one", "both of them", "the scarf one" become the
            # explicit IDs of orders discussed earlier, before the planner sees the message (services/conversation_memory.py).
            from .services.conversation_memory import recall
            rewritten, memory_notes = recall(request.message, state, self.tools)
            if memory_notes:
                request = request.model_copy(update={'message': rewritten})
                for n in memory_notes:
                    await self.step(emit, 'memory', f"\u201c{n['phrase']}\u201d \u2192 {' and '.join(n['order_ids'])}", source=n['from'], order_ids=n['order_ids'])
        if confirmed and role != 'manager':
            # Sprint 2: a planner key can read, draft and preview; only the manager key confirms a write.
            response = self.response(state, Classification(intent=state.last_intent or Intent.UNKNOWN, confidence=1), now,
                                     'A manager key is required to confirm this action. The preview stays open for a manager to confirm.', [], [])
            await self.tool_steps(emit, response)
            if emit: await emit(response.answer)
            state.revision += 1
            state.history = (state.history + [{'role': 'user', 'content': request.message}, {'role': 'assistant', 'content': response.answer}])[-16:]
            self.store.save(state)
            return response.model_copy(update={'state': state.model_copy(deep=True)})
        cancelled = request.message.strip().casefold().rstrip('.!。！') in {
            'cancel', 'cancel, do not send', 'do not send', "don't send", '取消', '不要发送', '取消发送'}
        if cancelled:
            state.pending_action = None
            state.pending_clarification = None
            state.chase_context = {}
            state.chase_drafts = []
            response = self.response(state, Classification(intent=state.last_intent or Intent.UNKNOWN, confidence=1),
                now, 'Cancelled. No pending action remains; nothing was sent.', [], [])
            if emit: await emit(response.answer)
        elif confirmed:
            response = await self.confirm(request, state, now)
            await self.tool_steps(emit, response)
            if emit:
                await emit(response.answer)
        elif (drafted := re.match(r'^\s*review the drafted chase-up for (ORD-\d{3})\s*\.?\s*$', request.message, re.I)):
            # "Review & send" on a home-screen draft (services/ready_drafts.py): the button's own words, not the planner's reading.
            response = await self.drafted_chase(drafted[1].upper(), classifier, state, now, emit)
        elif getattr(self, 'order_records', None) and (managed := record_preview(self, request.message, state, now, request.selected_order_id)) is not None:
            response = managed
            if emit: await emit(response.answer)
        elif hasattr(classifier, 'plan'):
            response = await self.converse(request, classifier, state, now, emit)
        else:
            # Any new turn revokes the old preview, including revisions and topic changes.
            state.pending_action = None
            classification = await classifier.classify(request.message, state, now)
            if classification.intent == Intent.MORNING_BRIEFING and hasattr(self, 'morning_handler'):
                response = await self.morning_handler(classification, state, now)
            elif classification.intent == Intent.REVIEW_REASON and hasattr(self, 'review_reason_handler'):
                response = await self.review_reason_handler(request, classification, state, now)
            else:
                response = self.route(request.message, classification, state, now)
        if memory_notes:
            from .services.conversation_memory import note_line
            recall_calls = [ToolCall(name='recall_conversation', arguments={'phrase': n['phrase']}, result={'order_ids': n['order_ids'], 'from': n['from']})
                            for n in memory_notes]
            response = response.model_copy(update={'answer': note_line(memory_notes) + '\n\n' + response.answer,
                                                    'tool_calls': recall_calls + list(response.tool_calls)})
        self.remember_orders(request.message, response, state)
        state.revision += 1
        state.history = (state.history + [{'role': 'user', 'content': original_message},
                                         {'role': 'assistant', 'content': response.answer}])[-16:]
        self.store.save(state)
        return response.model_copy(update={'state': state.model_copy(deep=True)})

    async def drafted_chase(self, order_id: str, agent, state: DialogState, now: datetime, emit=None) -> ChatResponse:
        """A chase-up drafted before the manager asked (home screen, "Drafted for you"): the same text, rebuilt from the
        current record, goes through the typed chase-up's preview, so the manager confirms that exact email and the usual
        gates apply (recipient from Settings, record unchanged since the preview, 15-minute expiry). Nothing is sent here."""
        from .services import ready_drafts
        from .services.chase_chat import chase_chat
        result = Classification(intent=Intent.EXECUTION_CHASE, confidence=1, slots=Slots(order_ids=[order_id], action='send', draft_number=1))
        state.pending_action = None
        state.pending_clarification = None
        try:
            row = self.tools.refresh_order(order_id)
        except Exception:  # noqa: BLE001  (an ID not on file)
            row = None
        record = row.record if row else None
        if not record or record.get('status') != 'IN_PROGRESS':
            text = f"{order_id} is {'no longer in progress' if record else 'not in the records'}, so there is nothing to chase. Nothing was sent."
            response = self.response(state, result, now, text, [], [row] if row else [])
            if emit: await emit(text)
            return response
        draft = ready_drafts.compose(record, now.date())
        state.chase_drafts = [{'order_ids': [order_id], 'recipient': None, 'department': draft['department'], 'subject': draft['subject'],
                               'text': draft['text'], 'sent': False, 'reply_deadline': None, 'business_now': now.isoformat(),
                               'source_snapshots': {order_id: record}}]
        state.chase_context = {'order_ids': [order_id], 'request': f'Drafted chase-up for {order_id}'}
        state.last_intent = Intent.EXECUTION_CHASE
        state.active_order = order_id
        response = await chase_chat(self, 'Preview draft 1', result, state, now, agent, None)
        call = ToolCall(name='draft_chase', arguments={'order_id': order_id, 'source': f'drafted for you: in progress, no activity for {ready_drafts.STALLED_DAYS}+ days'},
                        result={'drafts': state.chase_drafts}, executed=False)
        lead = f"Drafted for you from the record: {order_id} has had no recorded activity for {draft['idle_days']} days." + ('' if state.pending_action else ' Nothing was sent.')
        response = response.model_copy(update={'answer': lead + '\n\n' + response.answer, 'tool_calls': [call] + list(response.tool_calls)})
        await self.tool_steps(emit, response)
        if emit: await emit(response.answer)
        return response

    def remember_orders(self, message: str, response: ChatResponse, state: DialogState) -> None:
        """Orders this turn was about: IDs the manager named (or memory resolved), the resolved order, a compared pair.
        Candidate lists are not remembered: being listed is not being discussed."""
        from .services.conversation_memory import remember
        named = [i for i in dict.fromkeys(re.findall(r'\bORD-\d{3}\b', message.upper())) if i in set(response.order_ids) | {response.selected_order_id} | set(state.comparison_orders)]
        ids = named + ([response.selected_order_id] if response.selected_order_id else []) + (state.comparison_orders if response.intent == Intent.ORDER_COMPARE else [])
        remember(state, list(dict.fromkeys(i for i in ids if i)))

    @staticmethod
    async def step(emit, phase: str, label: str, **detail) -> None:
        """Stream one step of how the answer is being made (planner, memory, a tool call, narration) to the UI."""
        if not emit:
            return
        try:
            await emit(label, kind='step', phase=phase, **detail)
        except TypeError:      # an emitter that only takes text (tests, the offline replay): steps are optional
            return

    @staticmethod
    def compact_arguments(arguments: dict) -> dict:
        skip = {('reference', 'none'), ('action', 'read'), ('chase_mode', 'single')}
        out = {}
        for k, v in arguments.items():
            if v in (None, [], '', {}, False) or (isinstance(v, str) and (k, v) in skip):
                continue
            text = v if isinstance(v, (int, float)) else ', '.join(map(str, v)) if isinstance(v, list) else str(v)
            out[k] = text if not isinstance(text, str) or len(text) <= 60 else text[:57] + '...'
            if len(out) == 6:
                break
        return out

    @staticmethod
    def result_summary(result: dict) -> str:
        if not isinstance(result, dict) or not result:
            return 'done'
        for key, label in (('candidates', 'matching order'), ('records', 'record'), ('orders', 'order'), ('drafts', 'draft'), ('rows', 'row')):
            if isinstance(result.get(key), list):
                n = len(result[key])
                return f'{n} {label}{"s" if n != 1 else ""}'
        if result.get('declined'):
            return 'declined: not in the data (' + str(result.get('reason', '')) + ')'
        if 'order_id' in result and 'current_stage' in result:
            return f"{result['order_id']}: {str(result['current_stage']).lower()}, due {result.get('due_date', '?')}"
        for key in ('verdict', 'status', 'risk_level', 'preliminary'):
            if isinstance(result.get(key), str):
                return f'{key.replace("_", " ")}: {result[key]}'
        if isinstance(result.get('risks'), dict):
            return f"{len(result['risks'])} risk assessments"
        return f'{len(result)} fields'

    async def tool_steps(self, emit, response: ChatResponse, ms: float | None = None) -> None:
        calls = list(response.tool_calls)
        for i, call in enumerate(calls):
            last = i == len(calls) - 1
            await self.step(emit, 'tool', call.name, arguments=self.compact_arguments(call.arguments), summary=self.result_summary(call.result),
                            executed=call.executed, ms=round(ms, 1) if (ms is not None and last) else None,
                            rows=len(response.evidence) if last else None)

    async def converse(self, request, agent, state, now, emit):
        from .conversation import summary_response
        started = perf_counter()
        await self.step(emit, 'plan', 'Understanding the question', model=getattr(agent, 'model', None) or 'planner')
        plan = await agent.plan(request.message, state, now)
        for task in plan.tasks:
            c = task.classification
            await self.step(emit, 'plan', c.intent.value, slots=self.compact_arguments(c.slots.model_dump()), confidence=round(c.confidence, 2),
                            ms=round((perf_counter() - started) * 1000, 1))
        single_order_intents = {Intent.ORDER_LOOKUP, Intent.ORDER_REFRESH, Intent.ORDER_RISK, Intent.ORDER_EXPEDITE, Intent.ORDER_FORECAST}
        expanded = []
        human_ids = set(re.findall(r'\bORD-\d{3}\b', request.message.upper()))
        for task in plan.tasks:
            ids = [i for i in task.classification.slots.order_ids if i in human_ids]
            if task.classification.intent in single_order_intents and len(ids) > 1:
                for oid in ids:
                    copy = task.model_copy(deep=True)
                    copy.classification.slots.order_ids = [oid]
                    expanded.append(copy)
            else:
                expanded.append(task)
        if len(expanded) > 10:
            return self.ask('Please limit the request to ten order operations.',state,plan.tasks[0].classification,now,[],[])
        responses = []
        # Keep drafts/topic slots, but a new turn requires a fresh execution preview.
        state.pending_action = None
        if sum(t.classification.intent.value.startswith('execution.') for t in plan.tasks) > 1 and not all(t.classification.intent == Intent.EXECUTION_CHASE for t in plan.tasks):
            return self.ask('Please prepare one action at a time for preview and confirmation. You can combine other queries.',
                state, plan.tasks[0].classification, now, [], [])
        if all(t.classification.intent == Intent.EXECUTION_CHASE for t in expanded):
            grounded = self.grounding_check(request.message, expanded[0].classification.slots, Intent.EXECUTION_CHASE, expanded[0].classification, state, now, [], [],
                                            list(dict.fromkeys(re.findall(r'\bORD-\d{3}\b', request.message.upper()))))
            if grounded is not None:
                if emit: await emit(grounded.answer)
                return grounded
            if state.comparison_orders and not human_ids and not expanded[0].classification.slots.draft_number and not self.describe_candidates(request.message, now):
                response = self.ask('Which order do you mean: ' + ', '.join(state.comparison_orders) + '?', state, expanded[0].classification, now, [], [], state.comparison_orders)
                if emit: await emit(response.answer)
                return response
            from .services.chase_chat import chase_chat
            t0 = perf_counter()
            response = await chase_chat(self, request.message, expanded[0].classification, state, now, agent, emit)
            await self.tool_steps(emit, response, (perf_counter() - t0) * 1000)
            return response
        for task in expanded:
            t0 = perf_counter()
            result = task.classification
            if result.intent == Intent.GENERAL:
                response = ChatResponse(answer='The model is unavailable. Please try your general question again later.', intent=Intent.GENERAL,
                    slots=Slots(), confidence=result.confidence, state=state, business_date=now.date().isoformat())
            elif result.intent in (Intent.ORDER_SUMMARY, Intent.RISK_OVERVIEW):
                response = self.grounding_check(request.message, result.slots, result.intent, result, state, now, [], [], list(dict.fromkeys(re.findall(r'\bORD-\d{3}\b', request.message.upper())))) \
                    or summary_response(self, result, state, now, request.message)
            else:
                if state.last_intent:
                    state.topics[state.last_intent.value] = {
                        'slots':state.slots.model_dump(mode='json'), 'active_order':state.active_order,
                        'comparison_orders':state.comparison_orders[:], 'review_draft_id':state.review_draft_id}
                saved = state.topics.get(result.intent.value)
                if task.resume and saved and result.intent != state.last_intent:
                    state.slots = Slots.model_validate(saved['slots'])
                    state.active_order = saved['active_order']
                    state.comparison_orders = saved['comparison_orders']
                    state.review_draft_id = saved.get('review_draft_id')
                    state.last_intent = result.intent
                if human_ids and result.slots.order_ids and result.intent != Intent.ORDER_COMPARE:
                    state.comparison_orders = []
                if result.intent.value.startswith('execution.'):
                    state.pending_action = None
                if result.intent == Intent.MORNING_BRIEFING and hasattr(self, 'morning_handler'):
                    response = await self.morning_handler(result, state, now)
                elif result.intent == Intent.REVIEW_REASON and hasattr(self, 'review_reason_handler'):
                    response = await self.review_reason_handler(request, result, state, now)
                else:
                    # Entity selection is grounded in the original human message, never planner prose.
                    explicit = set(re.findall(r'\bORD-\d{3}\b', request.message.upper()))
                    if result.slots.order_ids:
                        explicit &= set(result.slots.order_ids)
                    route_message = re.sub(r'\bORD-\d{3}\b',
                        lambda m:m[0] if m[0].upper() in explicit else '', task.message, flags=re.I)
                    if result.intent.value.startswith('execution.'):
                        route_message = request.message
                    response = self.route(route_message, result, state, now)
            responses.append(response)
            await self.tool_steps(emit, response, (perf_counter() - t0) * 1000)
        if len(responses) > 1 and all(r.intent == Intent.ORDER_COMMITMENT and not r.needs_clarification for r in responses):
            responses.insert(0, self.commitment_comparison(responses, state, now))
        queried = list(dict.fromkeys(i for r in responses if r.intent in single_order_intents for i in r.order_ids))
        if len(queried) > 1:
            state.comparison_orders = queried
            state.active_order = None
            state.last_order_ids = queried
            state.slots.order_ids = []
        await self.step(emit, 'narrate', 'Writing the answer from these results', model=getattr(agent, 'model', None) or 'narrator')
        answer = await agent.narrate(request.message, state, responses, emit)
        last = responses[-1]
        evidence = list({(e.source,e.row):e for r in responses for e in r.evidence}.values())
        return last.model_copy(update={'answer':answer, 'selected_order_id':state.active_order, 'tool_calls':[t for r in responses for t in r.tool_calls],
            'evidence':evidence,'sources':list(dict.fromkeys(e.source for e in evidence)),
            'order_ids':list(dict.fromkeys(i for r in responses for i in r.order_ids))[:10],
            'needs_clarification':any(r.needs_clarification for r in responses),
            'clarification_question':'\n'.join(r.clarification_question for r in responses if r.clarification_question) or None,
            'confirmation_required':state.pending_action is not None,
            'confirmation_id':state.pending_action.id if state.pending_action else None})

    @staticmethod
    def confirmation_word(message: str) -> bool:
        """场景 3.1–3.3：确认只认明确命令，不信任模型生成的布尔值。"""
        return message.strip().casefold().rstrip('.!。！') in {'send now', 'confirm send', 'save it', 'confirm', 'confirm save', 'confirm create', 'confirm update', '确认', '确认发送', '确认保存', '确认创建', '确认更新'}

    def response(self, state: DialogState, result: Classification, now: datetime, answer: str,
                 calls: list[ToolCall], evidence: list[Evidence], question: str | None = None) -> ChatResponse:
        """场景 1.1–3.3：统一返回结构和逐行证据，不让模型覆盖已计算结论。"""
        evidence = list({(e.source, e.row): e for e in evidence}.values())
        return ChatResponse(answer=answer, intent=result.intent, slots=state.slots,
                            confidence=result.confidence, needs_clarification=bool(question), clarification_question=question,
                            confirmation_required=state.pending_action is not None,
                            confirmation_id=state.pending_action.id if state.pending_action else None,
                            state=state, tool_calls=calls, evidence=evidence,
                            source_details=f'As of {now.isoformat()}; {getattr(self.tools, "freshness", "test fixture")}',
                            order_ids=state.last_order_ids[:10], selected_order_id=state.active_order,
                            sources=list(dict.fromkeys(e.source for e in evidence)), business_date=now.date().isoformat())

    def ask(self, question: str, state: DialogState, result: Classification, now: datetime,
            calls: list[ToolCall], evidence: list[Evidence], candidates: list[str] | None = None) -> ChatResponse:
        """场景 1.1/1.4/1.5/1.6/2.1/3.1–3.3：保存缺槽问题并追问最小区分信息。"""
        state.pending_clarification = PendingClarification(intent=result.intent, question=question,
                                                        slots=state.slots, candidates=candidates or [])
        return self.response(state, result, now, question, calls, evidence, question)

    def route(self, message: str, result: Classification, state: DialogState, now: datetime) -> ChatResponse:
        """场景 1.1–3.3：合并同意图槽位，再执行服务器约束。"""
        intent = result.intent
        previous_slots = state.slots
        previous_clarification = state.pending_clarification
        base = state.slots.model_dump() if state.last_intent == intent else Slots().model_dump()
        fresh = result.slots.model_dump(exclude_defaults=True)
        explicit_ids = list(dict.fromkeys(re.findall(r'\bORD-\d{3}\b', message.upper())))
        if explicit_ids:
            state.last_order_ids = explicit_ids
            state.active_order = explicit_ids[0] if len(explicit_ids) == 1 else None
            fresh['order_ids'] = explicit_ids
        elif 'order_ids' in fresh:
            # Model guesses are not entity resolution. Only the user's explicit IDs
            # (or previously server-resolved slots) may select an order.
            fresh.pop('order_ids')
        if intent == Intent.ORDER_LOOKUP and not explicit_ids and any(key in fresh for key in ('customer', 'product', 'quantity', 'due_date')):
            base['order_ids'] = []
        if 'order_ids' in fresh and intent not in (Intent.ORDER_COMPARE,):
            for key in ('customer', 'product', 'quantity', 'due_date'):
                base[key] = None
        base.update({k: v for k, v in fresh.items() if v is not None})
        slots = Slots.model_validate(base)
        # Read-action flags should not leak into a later command.
        slots.action = result.slots.action
        slots.reference = result.slots.reference
        state.slots = slots
        state.last_intent = intent
        state.pending_clarification = None
        calls: list[ToolCall] = []
        evidence: list[Evidence] = []
        # Sprint 3: "why eight same weekdays?" / "why not the last 7 days?" gets the measured reasons, whatever the planner chose.
        from .services import baseline_rationale
        if baseline_rationale.asks_why(message) and not intent.value.startswith('execution.'):
            state.pending_clarification = None
            calls.append(ToolCall(name='explain_baseline_choice', arguments={'windows_compared': sorted(baseline_rationale.STUDY)},
                                  result={'chosen': 8, 'study': {str(k): v for k, v in baseline_rationale.STUDY.items()}, 'source': 'analysis/baseline_window.py'}))
            return self.response(state, result, now, baseline_rationale.answer(), calls, evidence)
        # Sprint 2: refusals come before clarifications. A request for money, people, causes, deletions, cancellations or
        # customer contact gets the stated non-goal, never "which order?".
        declined = refusal(message) if intent in (Intent.UNKNOWN, Intent.UNANSWERABLE, Intent.GENERAL) or result.confidence < 0.65 else None
        if intent == Intent.UNANSWERABLE and not declined:
            declined = (slots.reason or 'other', 'That is not something this system can answer from its data: it holds orders, daily stage output and workshop profiles only. '
                        'Ask about an order, a customer, a stage or a new-order estimate.')
        if declined:
            reason, answer = declined
            state.pending_clarification = None
            result = result.model_copy(update={'intent': Intent.UNANSWERABLE})
            state.last_intent = Intent.UNANSWERABLE
            calls.append(ToolCall(name='explain_no_data', arguments={'reason': reason}, result={'declined': True, 'reason': reason, 'answer': answer}, executed=False))
            return self.response(state, result, now, answer, calls, evidence)
        # A description instead of an ID ("the order with 1500 tops", "the scarves", "orders stuck at washing", "orders overdue more
        # than 2 days", "the largest customer's orders") names its own candidates: one match is taken and stated, several are listed.
        describable = intent in (Intent.ORDER_LOOKUP, Intent.ORDER_REFRESH, Intent.ORDER_RISK, Intent.ORDER_EXPEDITE, Intent.EXECUTION_CHASE, Intent.EXECUTION_NOTE, Intent.EXECUTION_REMINDER, Intent.ORDER_FORECAST) \
            and not (intent == Intent.ORDER_FORECAST and re.search(r'lead time|how long|similar|past orders|typical|usually take|took', message.casefold()))
        if (describable and not explicit_ids and not slots.order_ids and slots.action not in ('send', 'revise', 'confirm_target', 'update') and not slots.draft_number

                and not re.search(r'\b(this order|that order|this one|that one|\bit\b|the first|the second|the other)\b|\bthe order\b(?! (with|of|for|that|which|from))', message.casefold())
                and not slots.department
                and re.search(r'\b(with|of|for|at|in|stuck|pending|phase|stage|overdue|overdued|late|largest|biggest|main|scar|beanie|vest|hood|cardigan|polo|sweater|crewneck|tops|accessor)\w*', message.casefold())):
            described = None if (self.foreign_stage(message) or self.foreign_order_numbers(message, explicit_ids)) else self.describe_candidates(message, now)
            open_ids = set((previous_clarification.candidates if previous_clarification else []) or []) | set(state.comparison_orders)
            reply_like = len(message.split()) <= 6 or re.match(r'^\W*(the|that|this)\b', message.casefold())
            if described and open_ids and reply_like and described[1] and {e.record['order_id'] for e in described[1]} & open_ids:
                described = None    # "the scarf order" after a candidate list narrows that list; the narrowing step below handles it
            if described and not described[0].startswith('reading ') and not (described[0].endswith('are overdue as of ' + now.date().isoformat()) and not re.search(r'\b(late|overdue|overdued)\b', message.casefold())):
                label, rows = described
                if len(rows) == 1 and not re.search(r'\ball\b', message.casefold()):
                    slots.order_ids = [rows[0].record['order_id']]
                    slots.reference = 'explicit'
                    state.comparison_orders = []
                    calls.append(self.candidate_call(rows, now, description=label))
                elif rows:
                    evidence.extend(rows)
                    calls.append(self.candidate_call(rows, now, description=label))
                    state.active_order = None
                    state.chase_context = {}
                    state.last_order_ids = [e.record['order_id'] for e in rows]
                    options = '; '.join(self.candidate_hint(e.record, now) for e in rows)
                    return self.ask(f'Which one? {label}: {options}. Give the order ID' + (', or say "all of them" for a summary draft.' if intent == Intent.EXECUTION_CHASE else '.'), state, result, now, calls, evidence, state.last_order_ids)
                else:
                    calls.append(self.candidate_call(rows, now, description=label))
                    return self.response(state, result, now, label[0].upper() + label[1:] + '.', calls, evidence)
        # Sprint 2 (cause B): after a candidate list, narrow deterministically on the words the manager used
        # ("the scarf order", "the 500-piece one", "due 20 April") instead of depending on the planner's slots.
        candidates = previous_clarification.candidates if previous_clarification and previous_clarification.intent == Intent.ORDER_LOOKUP else []
        narrowed = False
        if intent == Intent.ORDER_LOOKUP and candidates and not explicit_ids:
            inferred = self.infer_lookup_slots(message, candidates, now)
            for key, value in inferred.items():
                if getattr(slots, key) in (None, [], ''):
                    setattr(slots, key, value)
            if inferred:
                narrowed = True
                slots.order_ids = list(candidates)  # restrict the search to the listed candidates
                state.slots = slots
        entity_free = (Intent.ORDER_COMPARE, Intent.ORDER_COMMITMENT, Intent.ORDER_PRIORITIZE, Intent.OPERATIONS_NORMALITY, Intent.OPERATIONS_DEVIATION,
                       Intent.OPERATIONS_OUTPUT, Intent.ORDER_RANK, Intent.WORKSHOPS, Intent.OPERATIONS_DISCOVERY)
        # A question about made-up orders ("a VIP customer order", "two orders need the same machines") gets the decision
        # rule and the data's limits, never a stale candidate list.
        policy = hypothetical_policy(message) if intent in (Intent.ORDER_COMPARE, Intent.ORDER_LOOKUP, Intent.ORDER_RISK, Intent.ORDER_PRIORITIZE, Intent.ORDER_EXPEDITE, Intent.UNKNOWN, Intent.GENERAL) and not explicit_ids and not slots.customer else None
        if policy:
            state.comparison_orders = []
            state.pending_clarification = None
            calls.append(ToolCall(name='explain_no_data', arguments={'reason': 'hypothetical'}, result={'declined': False, 'reason': 'hypothetical orders; rule stated'}, executed=False))
            return self.response(state, result, now, policy, calls, evidence)
        # Grounding: an order, product, stage, customer or workshop that is not in the records is an answer in itself
        # (what is on file instead), never a guess, a stale candidate list or a crash.
        grounded = self.grounding_check(message, slots, intent, result, state, now, calls, evidence, explicit_ids)
        if grounded is not None:
            return grounded
        if state.comparison_orders and not explicit_ids and not narrowed and intent not in entity_free:
            if mentions_order_reference(message) or slots.reference in ('active', 'ambiguous'):
                return self.ask('Which order do you mean: ' + ', '.join(state.comparison_orders) + '?', state, result, now, calls, evidence)
            state.comparison_orders = []   # the new question does not point at the compared orders at all
        if result.confidence < 0.65 or intent == Intent.UNKNOWN:
            if re.fullmatch(r'\W*(ok|okay|k|yep|yes|yeah|sure|fine|sounds good|great|thanks|thank you|noted|got it|alright|cool)\W*', message.casefold()) \
                    or re.search(r'\b(draft|message|email|mail)\b.*\b(looks? (fine|good|ok|okay)|sounds? (good|fine|right)|is fine)\b|^\W*(okay|ok|yep|yes)\b.*\b(draft|message|email)\b', message.casefold()):
                unsent = [d for d in state.chase_drafts if not d.get('sent')]
                if unsent:
                    d = unsent[-1]
                    text = (f"Nothing is waiting for confirmation. Draft {len(state.chase_drafts)} for {', '.join(d.get('order_ids', []))} is still unsent; "
                            f"say \"preview draft {len(state.chase_drafts)}\" to review it and then \"send now\" to send it, or ask about another order.")
                else:
                    text = 'Nothing is waiting for confirmation and nothing was changed. Ask about an order, a stage, or say what to draft, note or watch.'
                return self.response(state, result, now, text, calls, evidence)
            return self.ask(result.clarification_question or 'Which order or operation would you like to check?', state, result, now, calls, evidence)
        comparative_ranking = intent == Intent.ORDER_COMPARE and (slots.action == 'rank' or slots.criterion is not None)
        # "The order is at which stage now?" / "has it moved?" after any turn that put one order in focus: the order in focus,
        # whatever the planner labelled the reference, unless a candidate list is still open or the words describe something else.
        if (state.active_order and not explicit_ids and not slots.order_ids and not slots.customer and not slots.product and not slots.quantity
                and not state.comparison_orders and intent not in entity_free and intent not in (Intent.ORDER_FORECAST,)
                and (slots.reference == 'active' or re.search(r'\b(this|that|the) (order|one)\b|\bit\b|^\W*order (at|status|stage|progress|where)', message.casefold()))
                and not re.search(r'\borders\b|\b(with|of) \d|\b(order|orders) (with|from|for|that|which|due)\b|\border at (knitting|assembly|washing|packing)\b', message.casefold())):
            slots.order_ids = [state.active_order]
            slots.reference = 'active'
            state.slots = slots
        if (slots.reference == 'ambiguous' and not comparative_ranking) or (state.comparison_orders and slots.reference == 'active' and not slots.order_ids and intent != Intent.ORDER_COMPARE):
            described = self.describe_candidates(message, now) if not explicit_ids and not slots.customer and not slots.product and not (slots.order_ids and slots.reference == 'active') else None
            if described and len(described[1]) == 1 and described[0].startswith('reading '):
                # "55 status" / "show me status of 55": the only reading is ORD-055; take it and say so
                slots.order_ids = [described[1][0].record['order_id']]
                slots.reference = 'explicit'
                state.comparison_orders = []
                calls.append(self.candidate_call(described[1], now, description=described[0]))
                described = None
            elif state.comparison_orders and (mentions_order_reference(message) and not described):
                return self.ask('Which order do you mean: ' + ', '.join(state.comparison_orders) + '?', state, result, now, calls, evidence)
            elif state.comparison_orders and not described:
                state.comparison_orders = []   # the new question does not pick from the compared or listed orders
            if slots.order_ids and slots.reference == 'explicit':
                pass
            elif intent not in entity_free and not explicit_ids and not slots.customer and not slots.product:
                # "the order that was late yesterday": nothing is being compared, so the description itself names the candidates
                if described:
                    label, rows = described
                    if not rows:
                        calls.append(self.candidate_call(rows, now, description=label))
                        return self.response(state, result, now, label[0].upper() + label[1:] + '.', calls, evidence)
                    evidence.extend(rows)
                    calls.append(self.candidate_call(rows, now, description=label))
                    state.active_order = None
                    state.last_order_ids = [e.record['order_id'] for e in rows]
                    options = '; '.join(self.candidate_hint(e.record, now) for e in rows)
                    return self.ask(f'Which one? {label}: {options}. Give the order ID.', state, result, now, calls, evidence, state.last_order_ids)
                return self.ask('Which order ID, customer or product?', state, result, now, calls, evidence)
        if slots.due_date:
            try:
                slots.due_date = resolve_date(slots.due_date, now).isoformat()
            except ValueError:
                return self.ask('What is the explicit due date (YYYY-MM-DD)?', state, result, now, calls, evidence)

        if intent == Intent.ORDER_LOOKUP:
            if not any((slots.order_ids, slots.customer, slots.product, slots.quantity, slots.due_date)):
                described = self.describe_candidates(message, now)
                if described:
                    label, rows = described
                    evidence.extend(rows)
                    calls.append(self.candidate_call(rows, now, description=label))
                    state.active_order = None
                    state.last_order_ids = [e.record['order_id'] for e in rows]
                    options = '; '.join(self.candidate_hint(e.record, now) for e in rows)
                    return self.ask(f'Which one? {label}: {options}. Give the order ID.', state, result, now, calls, evidence, state.last_order_ids)
                return self.ask('Which order ID, customer or product?', state, result, now, calls, evidence)
            matches = self.tools.search_orders(slots)
            evidence.extend(matches)
            calls.append(ToolCall(name='search_orders', arguments=slots.model_dump(), result={'candidates': [e.record for e in matches]}))
            if len(matches) != 1:
                state.active_order = None
                options = '; '.join(f"{e.record['order_id']}: {e.record['product']}, {e.record['pieces']} pieces, due {e.record['due_date']}" for e in matches)
                state.last_order_ids = [e.record['order_id'] for e in matches]
                if matches and slots.customer and re.search(r'anything|any (issue|problem|trouble)|is?sues?|problems?|trouble|act on|attention|in trouble|worr|need to (do|act|know)', message.casefold()) and not slots.product and not slots.quantity:
                    return self.customer_summary(slots.customer, matches, state, result, now, calls, evidence)
                return self.ask(('Several matching orders. Which order ID, quantity or due date? ' + options) if matches else 'No matching order. Please check the order ID, quantity or due date.', state, result, now, calls, evidence, state.last_order_ids)
            order = self.select(matches[0].record['order_id'], state, calls, evidence)
            answer = self.order_facts(order)
        elif intent == Intent.ORDER_COMPARE:
            customers = self.customers_named(message)
            if not customers and not explicit_ids and not result.slots.order_ids and re.search(r'which customer|whose|customers?\b.*(share|most|more|greater|worst)|(share|most|more|greater|worst).*\bcustomers?\b', message.casefold()):
                customers = sorted({e.record['customer'] for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS'})   # no names given: rank them all
            if len(customers) >= 2 and not explicit_ids:
                state.comparison_orders = []
                state.pending_clarification = None
                answer, call, rows = self.compare_customers(customers, now, message)
                calls.append(call)
                evidence.extend(rows)
                return self.response(state, result, now, answer, calls, evidence)
            ids = slots.order_ids or state.comparison_orders
            if len(set(ids)) != 2:
                return self.ask('Which two distinct order IDs should I compare?', state, result, now, calls, evidence)
            state.comparison_orders = ids
            state.active_order = None
            state.last_order_ids = ids
            lowered = message.casefold()
            # "which has the higher delivery risk, considering due date, stage, last update and blockers?" ranks at once;
            # a bare "which one is more risky?" after a comparison still asks (dialogue design row 16: ask, do not guess)
            names_criteria = re.search(r'due|deadline|stage|update|activity|blocker|idle|moved|consider', lowered)
            wants_risk = (slots.criterion == 'risk' or 'delivery risk' in lowered or 'likely to be late' in lowered
                          or bool(re.search(r'\brisk', lowered) and names_criteria))
            if wants_risk:
                slots.criterion = 'risk'
                slots.action = 'rank'
                for f in ('due_date', 'current_stage', 'last_activity_date', 'status'):
                    if f not in slots.comparison_fields:
                        slots.comparison_fields.append(f)
            elif slots.action == 'rank' and not result.slots.criterion and not slots.criterion:
                if re.search(r'due|deadline|soon', lowered):
                    slots.criterion = 'due_date'
                elif re.search(r'recent|update|activity|quiet|idle|moved', lowered):
                    slots.criterion = 'last_activity_date'
            if re.search(r'pace|per (available )?(working )?day|daily (completion )?rate|workload|higher rate|tighter|tougher|pressure', lowered) and not wants_risk:
                answer, call, rows = self.compare_pace(ids, now)
                calls.append(call)
                evidence.extend(rows)
                return self.response(state, result, now, answer, calls, evidence)
            if not slots.comparison_fields:
                return self.ask('Which aspect matters: due date, stage, latest activity, status, pieces or overall delivery risk?', state, result, now, calls, evidence)
            rows = [self.tools.refresh_order(i) for i in ids]
            evidence.extend(rows)
            calls.append(ToolCall(name='compare_orders', arguments={'order_ids': ids, 'fields': slots.comparison_fields}, result={'records': [e.record for e in rows]}))
            if slots.action == 'rank' and not slots.criterion:
                return self.ask('Should I rank by overall delivery risk, due-date pressure or update recency?', state, result, now, calls, evidence)
            answer = '| Order | ' + ' | '.join(slots.comparison_fields) + ' |\n| --- | ' + ' | '.join('---' for _ in slots.comparison_fields) + ' |\n'
            answer += '\n'.join('| ' + e.record['order_id'] + ' | ' + ' | '.join(e.record[f] for f in slots.comparison_fields) + ' |' for e in rows)
            if slots.criterion != 'risk' and 'due_date' in slots.comparison_fields and rows[0].record['due_date'] != rows[1].record['due_date']:
                first = min(rows, key=lambda e: e.record['due_date'])
                other = next(e for e in rows if e is not first)
                answer += (f"\n{first.record['order_id']} first: its due date {first.record['due_date']} is earlier than {other.record['order_id']}'s {other.record['due_date']}"
                           + (f" ({(datetime.fromisoformat(now.date().isoformat()).date() - datetime.fromisoformat(first.record['due_date']).date()).days} days overdue)." if first.record['due_date'] < now.date().isoformat() else '.'))
            if slots.criterion == 'risk':
                risks = {e.record['order_id']: self.tools.assess_risk(e, now) for e in rows if e.record['status'] == 'IN_PROGRESS'}
                calls.append(ToolCall(name='assess_order_risk', arguments={'order_ids': list(risks)}, result={'risks': risks}))
                rank = {'overdue': 0, 'high': 1, 'medium': 2, 'unknown': 3, 'low': 4}
                ordered = sorted(risks, key=lambda i: (rank.get(risks[i]['risk_level'], 5), -(risks[i].get('late_days_best') or 0), risks[i]['days_to_due'], i))
                lines = []
                for i in ordered:
                    r = risks[i]
                    rec = next(e.record for e in rows if e.record['order_id'] == i)
                    lines.append(f"{i}: {r['risk_level']} \u2014 {r['reasons'][0].rstrip('.')}; stage {rec['current_stage']}, last activity {rec['last_activity_date']} ({r['idle_days']} days ago)" + (' (suspected stalled)' if r.get('stalled') else '') + '.')
                for e in rows:
                    if e.record['status'] != 'IN_PROGRESS':
                        lines.append(f"{e.record['order_id']}: no delivery risk \u2014 status {e.record['status']}" + (f", completed {e.record['completed_date']}" if e.record.get('completed_date') else '')
                                     + (f", recorded days late {e.record['days_late']}" if e.record.get('days_late') not in (None, '') else '') + '; nothing left to chase.')
                answer += '\nDelivery risk by the shared queue (late > high > medium > low, then the finish after the due date):\n' + '\n'.join(lines)
                answer += '\nBlockers: not recorded in this data; a gap in activity is a review trigger, not a blocker.'
                if ordered:
                    answer += f' Higher delivery risk: {ordered[0]}.'
                calls.append(ToolCall(name='rank_comparison', arguments={'criterion': 'risk'}, result={'order_ids': ordered}))
            elif slots.criterion:
                active = [e for e in rows if e.record['status'] == 'IN_PROGRESS']
                ranked = sorted(active, key=lambda e: (e.record[slots.criterion], e.record['order_id']))
                answer += '\nTransparent rule: ' + slots.criterion + ' ascending among unfinished orders; completed orders do not need a delivery chase. '
                answer += ('Review ' + ranked[0].record['order_id'] + ' first.') if ranked else 'Both orders are complete.'
                calls.append(ToolCall(name='rank_comparison', arguments={'criterion': slots.criterion}, result={'order_ids': [e.record['order_id'] for e in ranked]}))
        elif intent == Intent.ORDER_PRIORITIZE:
            history = refusal(message)
            if history and history[0] == 'history':
                calls.append(ToolCall(name='explain_no_data', arguments={'reason': 'history'}, result={'declined': True, 'reason': 'history'}, executed=False))
                return self.response(state, result, now, history[1], calls, evidence)
            lowered = message.casefold()
            # "orders overdue 2 days ago" / "due two days ago": the orders whose due date was that day
            ago = re.search(r'\b(\d+|one|two|three|four|five|six|seven)\s*(?:days?|d)\s+ago\b', lowered)
            if ago and re.search(r'due|overdue|overdued|late', lowered):
                n = int(ago[1]) if ago[1].isdigit() else {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7}[ago[1]]
                day = (now.date() - timedelta(days=n)).isoformat()
                due_rows = [e for e in self.tools.rows('orders.csv') if e.record['due_date'] == day]
                calls.append(ToolCall(name='search_orders', arguments={'due_date': day}, result={'candidates': [e.record for e in due_rows]}))
                evidence.extend(due_rows)
                active = [e for e in due_rows if e.record['status'] == 'IN_PROGRESS']
                if not due_rows:
                    overdue = sorted([e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS' and e.record['due_date'] < now.date().isoformat()], key=lambda e: e.record['due_date'])
                    text = f'No orders were due on {day} ({n} days ago), so none is overdue from that day. Overdue active orders as of {now.date().isoformat()}: ' + ', '.join(f"{e.record['order_id']} (due {e.record['due_date']})" for e in overdue) + '.'
                else:
                    text = f'Orders due on {day}: ' + '; '.join(f"{e.record['order_id']} ({e.record['customer']}, {e.record['pieces']} {e.record['product']}) {e.record['status']} at {e.record['current_stage']}" for e in due_rows) + '.' + (' None is still in progress.' if not active else '')
                state.last_order_ids = [e.record['order_id'] for e in due_rows]
                return self.response(state, result, now, text, calls, evidence)
            MON = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*'
            DAYX = r'(?:\d{1,2}(?:st|nd|rd|th)?(?:\s+' + MON + r')?|' + MON + r'\s+\d{1,2}(?:st|nd|rd|th)?|\d{4}-\d{2}-\d{2})'
            span = re.search(r'\b(?:between|from|due)\s+(' + DAYX + r')\s+(?:and|to|-|–|until|till)\s+(' + DAYX + r')\b', lowered)
            if span:
                def _day(t):
                    try: return parse_day(t, now)
                    except Exception: return None
                a, b = _day(span.group(1)), _day(span.group(2))
                if b and not a and re.fullmatch(r'\d{1,2}(st|nd|rd|th)?', span.group(1).strip()):
                    a = b.replace(day=int(re.sub(r'\D', '', span.group(1))))      # "from 1 to 11 June"
                if a and not b and re.fullmatch(r'\d{1,2}(st|nd|rd|th)?', span.group(2).strip()):
                    b = a.replace(day=int(re.sub(r'\D', '', span.group(2))))      # "June 1 to 11"
                if a and b and b >= a:
                    due_rows = sorted([e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS' and a.isoformat() <= e.record['due_date'] <= b.isoformat()], key=lambda e: e.record['due_date'])
                    calls.append(ToolCall(name='search_orders', arguments={'due_from': a.isoformat(), 'due_to': b.isoformat(), 'status': 'IN_PROGRESS'}, result={'candidates': [e.record for e in due_rows]}))
                    if not due_rows:
                        latest_due = max(e.record['due_date'] for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS')
                        text = f"No active orders are due between {a.isoformat()} and {b.isoformat()}: the latest due date among active orders is {latest_due} (business date {now.date().isoformat()}). Nothing in that window can slip yet; ask about the coming week for today's risks."
                        return self.response(state, result, now, text, calls, evidence)
                    evidence.extend(due_rows)
                    risks = {e.record['order_id']: self.tools.assess_risk(e, now) for e in due_rows}
                    lines = [f"{e.record['order_id']} ({e.record['customer']}, {e.record['pieces']} {e.record['product']}, {e.record['current_stage'].lower()}, due {e.record['due_date']}): {risks[e.record['order_id']]['risk_level']}" for e in due_rows]
                    state.last_order_ids = [e.record['order_id'] for e in due_rows]
                    return self.response(state, result, now, f"Active orders due {a.isoformat()} to {b.isoformat()}, with the queue's risk level:\n" + '\n'.join(lines), calls, evidence)
            if slots.window_days is None:
                if re.search(r'this week|next (seven|7) days|7 days', lowered):
                    slots.window_days = 7
                elif re.search(r'\b(hidden|beyond|after accounting|risk of missing|will miss|on schedule today)\b', lowered) or slots.criterion == 'risk':
                    slots.window_days = 7   # a risk ranking looks at the coming week, not only today
                else:   # the dialogue design asks "today only or the next seven days?" rather than guessing
                    return self.ask('Due today only, or include the next seven days? Overdue active orders will be included.', state, result, now, calls, evidence)
            data, rows = self.tools.prioritize(slots, now)
            evidence.extend(rows)
            calls.append(ToolCall(name='prioritize_orders', arguments={'window_days': slots.window_days, 'customer': slots.customer}, result=data))
            stage_filter = (slots.stage or '').upper() if slots.stage else None
            if not stage_filter:
                st = re.search(r'\b(?:in|at|currently in|from) (knitting|assembly|washing|packing)\b', lowered)
                stage_filter = st[1].upper() if st else None
            if stage_filter:
                rows = [e for e in rows if e.record['current_stage'] == stage_filter] or [e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS' and e.record['current_stage'] == stage_filter]
                rows = sorted(rows, key=lambda e: (e.record['due_date'], e.record['last_activity_date'], e.record['order_id']))
                data = dict(data, rule=f"Only orders at {stage_filter.lower()}. " + data['rule'], window_start=data['window_start'], window_end=data['window_end'])
                calls.append(ToolCall(name='search_orders', arguments={'current_stage': stage_filter, 'status': 'IN_PROGRESS'}, result={'candidates': [e.record for e in rows]}))
            state.last_order_ids = [e.record['order_id'] for e in rows]
            if re.search(r'which customer|whose|per customer|by customer|customer (needs|should|first)', lowered) and not slots.customer:
                groups: dict[str, list] = {}
                for e in rows: groups.setdefault(e.record['customer'], []).append(e)
                today = now.date()
                def worst(es): return max((today - datetime.fromisoformat(e.record['due_date'] + 'T00:00:00').date()).days for e in es)
                order = sorted(groups, key=lambda c: (-sum(1 for e in groups[c] if e.record['due_date'] < today.isoformat()), -worst(groups[c]), c))
                lines = []
                for c in order:
                    es = groups[c]; late = [e for e in es if e.record['due_date'] < today.isoformat()]
                    lines.append(f"{c}: {len(late)} overdue of {len(es)} in the window" + (f" (worst {worst(late)} days: " + ', '.join(f"{e.record['order_id']} {e.record['pieces']} {e.record['product']} at {e.record['current_stage'].lower()}" for e in late) + ')' if late else ''))
                verdict = f"{order[0]} first: " + ('the most overdue orders and the longest overdue.' if len(order) > 1 else 'the only customer with orders in the window.') if order else 'No customer has orders in the window.'
                calls.append(ToolCall(name='prioritize_orders', arguments={'group_by': 'customer', 'window_days': slots.window_days}, result={'order': order, 'lines': lines}))
                text = f"By customer, {data['window_start']} to {data['window_end']} (overdue active orders first; business date {today.isoformat()}):\n" + '\n'.join(lines) + '\n' + verdict + ' Owner and escalation time are not recorded.'
                return self.response(state, result, now, text, calls, evidence)
            if slots.criterion == 'risk' or re.search(r'risk of missing|hidden (delivery )?risk|will miss|too little remaining time|on schedule today', lowered):
                risks = {e.record['order_id']: self.tools.assess_risk(e, now) for e in rows}
                rank = {'overdue': 0, 'high': 1, 'medium': 2, 'unknown': 3, 'low': 4}
                rows = sorted(rows, key=lambda e: (rank.get(risks[e.record['order_id']]['risk_level'], 5), -(risks[e.record['order_id']].get('late_days_best') or 0), e.record['due_date']))
                hidden = [e for e in rows if risks[e.record['order_id']]['risk_level'] == 'high' and e.record['due_date'] >= now.date().isoformat()]
                data = dict(data, rule='Ranked by delivery risk: overdue first, then orders whose best-case finish is already after the due date (late days, most first), then due date. ' + (('Not yet overdue but will miss even in the best case: ' + ', '.join(e.record['order_id'] for e in hidden) + '. ') if hidden else ''))
                calls.append(ToolCall(name='assess_order_risk', arguments={'order_ids': [e.record['order_id'] for e in rows]}, result={'risks': {k: {'risk_level': v['risk_level'], 'late_days_best': v.get('late_days_best')} for k, v in risks.items()}}))
                state.last_order_ids = [e.record['order_id'] for e in rows]
            words = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
            # "top 3 orders", "which three production exceptions", "the five most urgent items"
            limit_re = r'\b(?:top|first|which|the)?\s*(\d{1,2}|' + '|'.join(words) + r')\s+(?:(?:most |biggest |largest )?[a-z-]+\s+)?(?:orders?|exceptions?|items?|issues?|things?|problems?|priorit(?:y|ies)|risks?)\b'
            limit_match = re.search(limit_re, lowered)
            if not limit_match and previous_clarification and previous_clarification.intent == intent:
                # "Which three exceptions ...?" -> "Today only.": the count was in the question that the clarification answered
                asked = next((h['content'] for h in reversed(state.history) if h['role'] == 'user'), '')
                limit_match = re.search(limit_re, asked.casefold())
            limit = (int(limit_match[1]) if limit_match and limit_match[1].isdigit() else words.get(limit_match[1]) if limit_match else None) or len(rows)
            shown = rows[:limit]
            lines = []
            for i, e in enumerate(shown, 1):
                r = e.record
                risk = self.tools.assess_risk(e, now)
                days = risk['days_to_due']
                when = f"{-days} day{'s' if days != -1 else ''} overdue" if days < 0 else 'due today' if days == 0 else f'due in {days} day{"s" if days != 1 else ""}'
                finish = f"best-case finish {risk['best_date']}" if risk.get('best_date') else 'finish unavailable'
                idle = f"last activity {r['last_activity_date']} ({risk['idle_days']} d ago" + (', suspected stalled)' if risk.get('stalled') else ')')
                action = ('confirm a new date with the customer; chase the stage if idle' if days < 0 else
                          'expedite, outsource or re-date today' if (risk.get('late_days_best') or 0) >= 1 else 'confirm dispatch readiness')
                lines.append(f"{i}. {r['order_id']} ({r['customer']}, {r['pieces']} {r['product']}): {when}; stage {r['current_stage']}; {idle}; queue {risk['risk_level']}, {finish}. Action: {action}.")
            answer = (f"Top {len(shown)} of {len(rows)} for {data['window_start']} to {data['window_end']} (overdue active orders first; business date {now.date().isoformat()}). " + data['rule'] + '\n' + '\n'.join(lines))
            if len(rows) > len(shown):
                answer += f"\n{len(rows) - len(shown)} more in the window: " + ', '.join(e.record['order_id'] for e in rows[len(shown):]) + '.'
            answer += '\nOwner and escalation time are not recorded; the department is the order\u2019s current stage.'
            if slots.order_ids:
                requested = slots.order_ids[0]
                position = state.last_order_ids.index(requested) + 1 if requested in state.last_order_ids else None
                answer += f'\n{requested}: actual rank {position}; ' if position else f'\n{requested} is not in this exception list. '
                inspected = self.tools.refresh_order(requested)
                evidence.append(inspected)
                calls.append(ToolCall(name='refresh_order', arguments={'order_id': requested}, result=inspected.record))
                answer += self.order_facts(inspected)
            answer += '\nRanking indicates review urgency, not a prediction of failure.'
        elif intent == Intent.ORDER_COMMITMENT:
            lowered_c = message.casefold()
            assumed_point = None
            if not slots.delivery_point:
                if re.search(r'\b(deliver(ed|y)?|arrive|at the customer|to the customer|ship(ped)? to)\b', lowered_c):
                    slots.delivery_point = 'customer'
                elif re.search(r'\b(ready|finish(ed)?|produce|complete[d]?|make|maximum|max|how many|can we (do|handle))\b', lowered_c):
                    slots.delivery_point, assumed_point = 'factory', 'ready at the factory (say "delivered" if the date is a customer delivery date)'
                else:
                    return self.ask('Does the deadline mean ready at our factory or delivered to the customer?', state, result, now, calls, evidence)
            wants_max = not result.slots.quantity and bool(re.search(r'maximum|\bmax\b|how many|how much|at most|up to', lowered_c))
            if wants_max:
                slots.quantity = None   # a carried quantity from an earlier question is not the one being asked about
            if (not slots.quantity and not wants_max) or not slots.product or not slots.due_date:
                return self.ask('What product, quantity and explicit due date should I estimate?', state, result, now, calls, evidence)
            if resolve_date(slots.due_date, now) <= now.date():
                return self.ask('That date is not in the future. What new delivery date should I assess?', state, result, now, calls, evidence)
            if slots.product and self.foreign_product('', Slots(product=slots.product)):
                assumed_point = ((assumed_point + '; ') if assumed_point else '') + f"no {slots.product.lower()} orders in the history (products on file: {', '.join(sorted({e.record['product'] for e in self.tools.rows('orders.csv')}))}), so the estimate uses the size-based lead-time model and the shared queue only"
            if wants_max:
                best_q, probe, rows = self.max_quantity_by(slots, now)
                evidence.extend(rows)
                calls.append(ToolCall(name='estimate_capacity', arguments={**slots.model_dump(), 'search': 'largest quantity whose best-case finish is on or before the due date'}, result={'max_quantity': best_q, 'probe': probe}))
                due = resolve_date(slots.due_date, now).isoformat()
                if best_q == 0:
                    bc = probe['queue_projection']['best_case'] if probe.get('queue_projection') else {}
                    lead = (f"No new {slots.product.lower()} order of any size is ready by {due} in the queue model: {probe['queue_projection']['orders_ahead'] if probe.get('queue_projection') else 'the'} active orders due earlier occupy every stage, "
                            f"so even a 1-piece order finishes {bc.get('finish_date', 'later')} best case ({bc.get('working_days')} working days). It could only be met by giving it manager priority ahead of overdue orders, which the expedite check can quantify.")
                else:
                    lead = f"Up to about {best_q:,} {slots.product.lower()} by {due} ({slots.delivery_point}): the largest quantity whose best-case queue finish is on or before the due date, current orders only, no new arrivals. Conditional forecast, not a promise."
                answer = lead + ('\nAssumed ' + assumed_point + '.' if assumed_point else '') + '\nProbe at that quantity:\n' + json.dumps(probe, ensure_ascii=False, indent=2)
            else:
                data, rows = self.tools.capacity(slots, now)
                evidence.extend(rows)
                calls.append(ToolCall(name='estimate_capacity', arguments=slots.model_dump(), result=data))
                answer = self.commitment_lead(slots, data, now) + ('\nAssumed ' + assumed_point + '.' if assumed_point else '') + '\nConditional forecast, not a promise:\n' + json.dumps(data, ensure_ascii=False, indent=2)
        elif intent in (Intent.OPERATIONS_NORMALITY, Intent.OPERATIONS_DEVIATION, Intent.OPERATIONS_OUTPUT):
            return self.production(message, intent, result, slots, state, now, calls, evidence, previous_clarification)
        elif intent == Intent.OPERATIONS_DISCOVERY:
            topn = re.search(r'\btop\s+(\d{1,2}|three|four|five|six|seven|eight|nine|ten)\b|\b(\d{1,2}|three|four|five|six|seven|eight|nine|ten)\s+(?:issues|problems|things|items|findings)\b', message.casefold())
            if topn and slots.window_days is None:
                w = topn.group(1) or topn.group(2)
                slots.window_days = int(w) if w.isdigit() else {'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}[w]
            data, rows = self.tools.find_anomalies(slots, now)
            evidence.extend(rows)
            focus = self.stage_focus(now) if re.search(r'one (stage|workshop|line|team|area)|which (stage|workshop|line)|where should i move|focus|biggest risk reduction|most deadlines', message.casefold()) else None
            if focus:
                calls.append(ToolCall(name='stage_focus', arguments={}, result=focus))
            calls.append(ToolCall(name='find_anomalies', arguments={'customer': slots.customer, 'stage': slots.stage, 'limit': data['shown']}, result=data))
            state.last_order_ids = [f['entity'] for f in data['findings'] if f['entity'].startswith('ORD-')][:10]
            state.active_order = None
            if not data['findings']:
                answer = f"Nothing unusual in the recorded data as of {data['business_date']}: no sustained stage drop, no stalled customer, no overdue or near-due miss, no idle order."
            else:
                kind_summary = ', '.join(f"{v} {k.replace('_', ' ')}" for k, v in data['by_kind'].items())
                answer = ((f"Focus on {focus['stage'].lower()} today: {focus['why']}; that is where one stage's effort would reduce delivery risk most.\n" if focus else '') +
                          f"{data['total']} finding{'s' if data['total'] != 1 else ''} as of {data['business_date']} ({kind_summary}); top {data['shown']} by tier and score:\n" +
                          '\n'.join(f"{i}. [{f['tier']}] {f['title']}. {f['action']} (rule: {f['rule']})" for i, f in enumerate(data['findings'], 1)) +
                          '\n' + data['limits'])
        elif intent == Intent.ORDER_RANK:
            data, rows = self.tools.rank_active_orders(slots, now)
            lowered_r = message.casefold()
            near = re.search(r'near[- ]term|soon[- ]due|due soon|near due\b|near-due|ship(ping)? date|next (seven|7) days|this week', lowered_r)
            if near and data['criterion'] == 'idle_days':
                horizon = (now.date() + timedelta(days=slots.window_days or 7)).isoformat()
                full, full_rows = self.tools.rank_active_orders(Slots(criterion='idle_days', window_days=34, customer=slots.customer), now)
                keep = [o for o in full['orders'] if now.date().isoformat() <= o['due_date'] <= horizon][:10]
                data = dict(data, orders=keep, rule=f"Only active orders due between {now.date().isoformat()} and {horizon} (not yet overdue), most idle first. " + data['rule'])
                rows = [e for e in full_rows if e.record['order_id'] in {o['order_id'] for o in keep}] or rows
            if re.search(r'quantity|piece[- ]?count|movement|handoff|hand-off|bottleneck|progressing inside', lowered_r):
                data = dict(data, rule=data['rule'] + ' The log records no piece counts per order and no stage hand-off dates: only the current stage and the last activity date, so movement inside a stage cannot be seen; idle days are the only signal.')
            evidence.extend(rows)
            calls.append(ToolCall(name='rank_active_orders', arguments={'criterion': data['criterion'], 'customer': slots.customer, 'limit': len(data['orders'])}, result=data))
            state.last_order_ids = [o['order_id'] for o in data['orders']]
            state.active_order = None
            answer = (f"Active orders ranked by {data['criterion'].replace('_', ' ')} (business date {data['business_date']}). {data['rule']}\n" +
                      '\n'.join(f"{i}. {o['order_id']} ({o['customer']}, {o['pieces']} {o['product']}): last activity {o['last_activity_date']} ({o['idle_days']} days ago), due {o['due_date']}, stage {o['current_stage']}." for i, o in enumerate(data['orders'], 1)))
        elif intent == Intent.WORKSHOPS:
            data, rows = self.tools.list_workshops(slots)
            evidence.extend(rows)
            calls.append(ToolCall(name='list_workshops', arguments={'category': data['category'], 'quantity': slots.quantity}, result=data))
            answer = ('Eligible outside workshops' + (f" for {data['category'].lower()}" if data['category'] else '') + (f", {slots.quantity}-piece batch" if slots.quantity else '') + ': ' +
                      ('; '.join(f"{w['workshop_id']} {w['name']} ({w['capacity_pieces_per_day']}/day, queue {w['current_queue_days']} d, pickup {w['pickup_lead_days']} d, defect batch risk {w['defect_batch_probability']:.0%}" + (f", about {w['estimated_batch_days']} days" if 'estimated_batch_days' in w else '') + ')' for w in data['eligible']) or 'none') +
                      '. Excluded: ' + ('; '.join(f"{w['workshop_id']} {w['name']} ({', '.join(w['excluded_because'])})" for w in data['excluded']) or 'none') + '. ' + data['limits'])
        elif intent == Intent.ORDER_FORECAST:
            ids = slots.order_ids
            if len(ids) > 1:
                return self.ask('Which order should I forecast: ' + ', '.join(ids) + '?', state, result, now, calls, evidence, ids)
            order_id = ids[0] if ids else state.active_order
            if not order_id and slots.quantity:
                return self.lead_time_for_size(slots, state, result, now, calls, evidence)
            if not order_id:
                return self.ask('Which order should I forecast? Please give its ID, or a size (for example "1,000 hoodies") for the typical lead time.', state, result, now, calls, evidence)
            try:
                order = self.select(order_id, state, calls, evidence)
            except ValueError:
                return self.not_found(order_id, state, result, now, calls, evidence)
            if order.record['status'] != 'IN_PROGRESS':
                answer = self.order_facts(order) + '\nThe lead-time forecast applies to orders still in progress; this one is complete.'
            else:
                from .prediction.aft import LeadTimeModel
                forecast = LeadTimeModel().forecast_order(order.record, now.date())
                calls.append(ToolCall(name='predict_order_delay', arguments={'order_id': order_id}, result=forecast))
                answer = (self.order_facts(order) + f"\nLead-time model: delay probability {forecast['delay_probability']:.0%} ({forecast['risk_level']}); expected completion {forecast['expected_completion_date']} "
                          f"(80% range {forecast['completion_range_80pct'][0]} to {forecast['completion_range_80pct'][1]}); typical lead time for {forecast['pieces']} pieces {forecast['typical_lead_days_for_this_size']} days. "
                          'A ranking from order size and elapsed time, not a schedule; the queue risk tool gives the dispatch view.')
        elif intent == Intent.EXECUTION_REMINDER and (slots.condition == 'stage_below_range' or (slots.stage and not slots.order_ids and not state.active_order)):
            # Sprint 2: a watch on a stage, not an order ("remind me tomorrow if packing is still behind").
            if not slots.stage:
                return self.ask('Which stage should I watch: knitting, assembly, washing or packing?', state, result, now, calls, evidence)
            slots.condition = 'stage_below_range'
            watch_id = f'STAGE:{slots.stage}'
            deadline = resolve_datetime(slots.deadline or '', now)
            if deadline is None and slots.deadline:
                try:
                    deadline = datetime.combine(resolve_date(slots.deadline, now), time(7), tzinfo=now.tzinfo)  # a date alone means the 07:00 briefing
                except ValueError:
                    deadline = None
            if deadline is None:
                return self.ask('When should I check: tomorrow at 07:00, or another date and time?', state, result, now, calls, evidence)
            if deadline <= now:
                return self.ask('The check time must be in the future. What date and time?', state, result, now, calls, evidence)
            slots.deadline = deadline.isoformat()
            existing = self.store.get_reminder(state.session_id, watch_id, 'stage_below_range')
            check_day = (deadline.date() - timedelta(days=1)).isoformat()
            preview = (f"{'Update existing' if existing else 'Create'} watch on {slots.stage.lower()}: at {deadline.isoformat()} compare its output on {check_day} "
                       f"with the previous eight same weekdays and notify you only if it is still below that range. Please confirm.")
            self.propose('reminder', watch_id, {'condition': 'stage_below_range', 'stage': slots.stage, 'deadline': deadline.isoformat(),
                                               'since': existing['since'] if existing else now.isoformat()}, preview, state, now)
            answer = preview
        else:
            ids = slots.order_ids
            correction = re.search(r'(ORD-\d{3})\b[^.]{0,12}\bnot (ORD-\d{3})', message, re.I)
            if correction and len(ids) > 1:
                ids = [correction[1]]          # "was for ORD-083, not ORD-038"
                slots.order_ids = ids
            note_read = bool(re.search(r"\b(is|are) (the|that|there a) note|already (have|has|got)|has anyone noted|what did (i|we) note|any note (on|for|about)|logged (it )?against|which order (has|holds|carries) the note", message.casefold()))
            if len(ids) > 1 and intent == Intent.EXECUTION_NOTE and ((not slots.text and '?' in message) or note_read):
                parts = []
                for oid in ids:
                    saved = self.saved_notes(oid)
                    parts.append(f"{oid}: " + ('; '.join(n.get('text', '') for n in saved[:5]) if saved else 'no saved note'))
                calls.append(ToolCall(name='save_internal_note', arguments={'order_ids': ids, 'action': 'read'}, result={'notes': parts}, executed=False))
                return self.response(state, result, now, 'Saved notes: ' + ' | '.join(parts) + '. Nothing was changed.', calls, evidence)
            if len(ids) > 1:
                return self.ask('Which order should I use: ' + ', '.join(ids) + '?', state, result, now, calls, evidence, ids)
            customer = detect_customer(message, self.tools) if not explicit_ids else None
            if customer:
                # "the Maple & Co order": only that customer's active orders count; one -> use it, more -> ask with hints
                matches = self.tools.search_orders(Slots(customer=customer))
                calls.append(self.candidate_call(matches, now, customer=customer))
                evidence.extend(matches)
                if len(matches) == 1:
                    ids = [matches[0].record['order_id']]
                    slots.order_ids = ids
                elif matches:
                    state.active_order = None
                    state.last_order_ids = [e.record['order_id'] for e in matches]
                    return self.ask(f"Which {customer} order? " + '; '.join(self.candidate_hint(e.record, now) for e in matches) + '. Give the order ID.', state, result, now, calls, evidence, state.last_order_ids)
                else:
                    return self.response(state, result, now, f'{customer} has no order in progress; its orders are all complete.', calls, evidence)
            order_id = ids[0] if ids else state.active_order
            if not order_id:
                return self.ask('Which order should I use? Please give its ID or customer.', state, result, now, calls, evidence)
            try:
                order = self.select(order_id, state, calls, evidence)
            except ValueError:
                return self.not_found(order_id, state, result, now, calls, evidence)
            if intent == Intent.ORDER_REFRESH:
                answer = self.order_facts(order) + '\nOnly last_activity_date is recorded; no event description is available. An unchanged record does not prove no work happened.'
                answer += ('\nThe last recorded activity date is today; author and time are not available.'
                           if order.record['last_activity_date'] == now.date().isoformat()
                           else f'\nNo update dated {now.date().isoformat()} is recorded.')
            elif intent == Intent.ORDER_EXPEDITE:
                data, rows = self.tools.expedite(order_id, now)
                evidence.extend(rows)
                calls.append(ToolCall(name='assess_expedite', arguments={'order_id': order_id}, result=data))
                answer = f"{order_id}: {data['recommendation']}. {data['reason']}"
                if data['gain'] is not None:
                    answer += (f"\nFinish: {data['finish_before']} → {data['finish_after']}. "
                               f"Lateness saved: {data['gain']} working days; added elsewhere: {data['cost']}; net: {data['net']}.")
                    answer += '\nAffected orders: ' + ('; '.join(
                        f"{o['order_id']}: {o['extra_days']:+} working days, added lateness {o['added_lateness']:+}" +
                        (' (newly late)' if o['newly_late'] else '') for o in data['affected']) or 'None.')
                answer += ('\nCurrent orders only, same capacity before and after. No schedule was changed. '
                           'Open Risk → Analyze expedite impact for manager review, or ask to draft a chase-up, save a note, or set a reminder.')
            elif intent == Intent.ORDER_RISK:
                risk = self.tools.assess_risk(order, now)
                calls.append(ToolCall(name='assess_order_risk', arguments={'order_id': order_id}, result=risk))
                # Plain-language status first (Sprint 2): recorded lateness is a fact, projected risk is a judgement.
                if order.record['status'] == 'COMPLETE':
                    status_line = f"Completed on {order.record['completed_date']}; recorded days late: {order.record['days_late']}."
                elif risk['days_to_due'] < 0:
                    status_line = (f"Already overdue: due {order.record['due_date']}, {-risk['days_to_due']} days ago, still at {order.record['current_stage']}."
                                   + (f" Best-case finish {risk['best_date']}, {risk['late_days_best']} working days after the due date (an estimate, not a promise)." if risk.get('best_date') else ''))
                else:
                    status_line = (f"Not past due, not delayed yet: due {order.record['due_date']}, {risk['days_to_due']} days away. "
                                   f"Projected risk {risk['risk_level']}: {risk['reasons'][0].rstrip('.')}.")
                status_line += f" Last recorded activity {order.record['last_activity_date']} ({risk['idle_days']} days before the business date); a gap is not proof of a stoppage."
                named = [st for st in stages_in(message) if st != order.record['current_stage']]
                if named and order.record['current_stage'] in STAGE_ORDER:
                    current = STAGE_ORDER.index(order.record['current_stage'])
                    for st in named:
                        if STAGE_ORDER.index(st) > current:
                            status_line += f" It is still at {order.record['current_stage'].lower()}, before {st.lower()}, so {article(st)} {st.lower()} problem cannot have affected it yet."
                        else:
                            status_line += f" It has already passed {st.lower()}; {article(st)} {st.lower()} problem would only matter if work were sent back."
                if re.search(r'trace|handoff|hand-off|originat|accumulat|diverge|timeline|history|first delayed|dwell|upstream delay|arrive[d]? (late )?into|build up|built up|while (in|at|it)|before (assembly|washing|packing|knitting)|stage[- ]by[- ]stage|evidence', message.casefold()):
                    status_line += (f" Stage-by-stage trace is not recorded: the order record holds only the current stage ({order.record['current_stage']}), the last activity date and the due date, "
                                    "with no stage-entry or hand-off dates, so where the delay first arose cannot be traced from this data; the stage event log would be needed.")
                answer = self.order_facts(order) + '\n' + status_line + '\nFacts and risk interpretation:\n' + json.dumps(risk, indent=2)
                answer += '\nA risk pattern does not establish that it will be late. Request a status update if needed.'
            else:
                return self.execution(message, result, state, now, calls, evidence, order, previous_slots)
        return self.response(state, result, now, answer, calls, evidence)

    # ------------------------------------------------------------------ production questions (2.1 / 2.2)
    def production(self, message, intent, result, slots, state, now, calls, evidence, previous_clarification):
        """Normality, deviation and output questions share one path (26 Oct question sheet, rows 20-39):
        - a period ("since 25 March", "late March", "the last three working days") -> production_window over every day;
        - no stage, or a comparative question ("which stage is most off") -> all four stages on the date;
        - invalid, Sunday and future dates are answers, not clarifications; a date after the log falls back to the latest record;
        - a clarification is never repeated: the second time, the stated default is used;
        - "is it because <workshop>" looks the workshop up and says what the data cannot link."""
        lowered = message.casefold()
        mentioned = stages_in(message)
        if not slots.stage and len(mentioned) == 1:
            slots.stage = mentioned[0]
        latest = self.tools.latest_log_date()
        repeated = bool(previous_clarification and previous_clarification.intent == intent)
        tool_name = {Intent.OPERATIONS_NORMALITY: 'check_normality', Intent.OPERATIONS_DEVIATION: 'explain_deviation', Intent.OPERATIONS_OUTPUT: 'get_production_output'}[intent]
        hypothesis = detect_workshop(message, self.tools) if re.search(r'because|due to|caused|cause|blame|suspend', lowered) else None

        def finish(answer, data, rows, name=None):
            evidence.extend(rows)
            calls.append(ToolCall(name=name or tool_name, arguments={k: v for k, v in slots.model_dump().items() if v not in (None, [], '')}, result=data))
            if hypothesis:
                answer += self.hypothesis_note(hypothesis, calls)
            return self.response(state, result, now, answer, calls, evidence)

        # 0. follow-ups on the previous production answer: the method ("what baseline did you use?") and the run
        #    ("did it only start yesterday?", "since when?", "how long?")
        method_q = re.search(r'\bbaselines?\b|compared? (?:it |that |this |them )?(?:with|to|against) what|what (?:did|do) you compare|how (?:did|do) you (?:calculate|compute|work (?:it|that|this) out|measure|judge|decide|get)', lowered)
        if method_q and not re.search(r'\d{4}-\d{2}-\d{2}|last week|same weekday', lowered):
            return finish(*self.baseline_answer(state, slots, now, latest))
        run_q = re.search(r'only start|since when|how long|when did (?:it|this|that) (?:start|begin)|first day|start(?:ed)? (?:only )?yesterday|just yesterday|one[- ]off|first time|been (?:going on|like this)', lowered)
        if run_q and slots.stage and not re.search(r'\d{4}-\d{2}-\d{2}', lowered):
            comp, rows = self.tools.stage_comparison(latest or now.date() - timedelta(days=1), now)
            item = next((x for x in comp['stages'] if x['stage'] == slots.stage), None)
            run = (item or {}).get('below_days_running') or 0
            if run >= 2:
                below_days = [date.fromisoformat(e.record['date']) for e in self.tools.rows('production_log.csv') if e.record['stage'] == slots.stage and e.record['date'] <= comp['date']]
                start = sorted(d0 for d0 in below_days if d0.weekday() != 6)[-run]
                period = {'start': start, 'end': date.fromisoformat(comp['date']), 'label': f"since {start.isoformat()}", 'capped': False}
                data, rows = self.tools.production_window(period, now, slots.stage)
                answer = (f"No. {slots.stage.title()} has been below its same-weekday range for {run} consecutive working days, since {start.isoformat()}; "
                          f"{comp['date']} was the latest of them, not the first.\n" + self.window_answer(data, slots.stage, intent, lowered))
                state.topics['production_window'] = {'start': period['start'].isoformat(), 'end': period['end'].isoformat(), 'label': period['label'], 'stage': slots.stage}
                return finish(answer, data, rows, 'production_window')
            if item and item.get('status') == 'below':
                answer = (f"Yes, as far as the log shows: {slots.stage.title()} was below its same-weekday range on {comp['date']} ({item['output']} pieces against {item['minimum']}\u2013{item['maximum']}) "
                          f"and inside it on the working day before, so this is one day, not a run yet. Check again after the next record.")
            else:
                answer = f"{slots.stage.title()} is not below its same-weekday range on the latest record ({comp['date']}), so there is no drop to date the start of."
            return finish(answer, comp, rows, 'stage_comparison')

        # 1. a period in the manager's words (or a planner target_date that is a period)
        period = resolve_period(message, now, latest) or (resolve_period(slots.target_date, now, latest) if slots.target_date else None)
        if period:
            stage = slots.stage if (slots.stage and not comparative_stage_question(message) and len(mentioned) <= 1) else None
            data, rows = self.tools.production_window(period, now, stage)
            answer = self.window_answer(data, stage, intent, lowered)
            state.topics['production_window'] = {'start': period['start'].isoformat(), 'end': period['end'].isoformat(), 'label': period.get('label', ''), 'stage': stage}
            return finish(answer, data, rows, 'production_window')

        # 2. the stage (asked once, before the date; the second time, all four stages are compared)
        all_stages = comparative_stage_question(message) or len(mentioned) > 1 or (not slots.stage and (repeated or intent != Intent.OPERATIONS_NORMALITY or slots.observed_output is None))
        if not slots.stage and not all_stages:
            return self.ask(STAGE_QUESTION + ('' if slots.target_date else ' And which date, if not yesterday?'), state, result, now, calls, evidence)

        # 3. the date: invalid, Sunday, future, missing
        target_text = slots.target_date
        if not target_text:
            m = re.search(r'\b(\d{4}-\d{2}-\d{2})\b|\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b|\b(yesterday|today|tomorrow)\b', lowered)
            target_text = m[0] if m else None
        hypothetical = slots.observed_output is not None and bool(re.search(r'\bif\b|would (that|it) be|\bis \d[\d,]* ?(pieces|pcs)? ?(a )?normal|normal day for|normal for', lowered)) and not re.search(r'\d{4}-\d{2}-\d{2}|\b\d{1,2}(st|nd|rd|th)? (march|april|february|january)|\bon (the )?\d{1,2}(st|nd|rd|th)\b|yesterday', lowered)
        if hypothetical:
            target_text = 'today'
        if not target_text and slots.observed_output is not None and not repeated:
            return self.ask(f'Which date is the {slots.observed_output}-piece {(slots.stage or "").lower()} figure for? ("today", "yesterday" or a date; I compare it with the same weekday in recent working weeks.)'.replace('  ', ' '), state, result, now, calls, evidence)
        if not target_text:
            target_text = 'yesterday'
            slots.target_date = 'yesterday'
        try:
            target = parse_day(target_text, now)
            if target is None:
                raise ValueError(target_text)
        except ValueError:
            bad = re.search(r'\d{4}-\d{2}-\d{2}', target_text)
            if bad:
                y, mth = int(bad[0][:4]), int(bad[0][5:7])
                import calendar
                days_in = calendar.monthrange(y, mth)[1] if 1 <= mth <= 12 else None
                note = f"{bad[0]} is not a valid date" + (f" ({calendar.month_name[mth]} {y} has {days_in} days)" if days_in else '') + '. ' + DATE_QUESTION
                return self.ask(note, state, result, now, calls, evidence)
            return self.ask(DATE_QUESTION, state, result, now, calls, evidence)
        slots.target_date = target.isoformat()
        if target.weekday() == 6:
            answer = (f"{target.isoformat()} was a Sunday: the factory is closed, no output is recorded for any stage, and a closed day is not compared with "
                      f"working-day levels. Ask about {(target - timedelta(days=1)).isoformat()} (Saturday) or {(target + timedelta(days=1)).isoformat()} (Monday) instead.")
            return finish(answer, {'date': target.isoformat(), 'status': 'closed', 'weekday': 'Sunday'}, [])
        if target > now.date():
            answer = (f"No record can exist for {target.isoformat()}: the business date is {now.date().isoformat()}" + (f" and the log ends {latest.isoformat()}" if latest else '') +
                      f". The question\u2019s premise cannot be checked yet. As of {latest.isoformat() if latest else 'the latest record'}: ")
            comp, rows = self.tools.stage_comparison(latest or now.date() - timedelta(days=1), now)
            answer += self.comparison_sentence(comp, slots.stage)
            return finish(answer, {'date': target.isoformat(), 'status': 'future', 'latest_record': latest.isoformat() if latest else None, 'latest_comparison': comp}, rows, 'stage_comparison')

        # 4. all stages (comparative question, no stage, or the second time we would have asked for one)
        if all_stages and (intent != Intent.OPERATIONS_OUTPUT or comparative_stage_question(message)):
            comp, rows = self.tools.stage_comparison(target, now)
            answer = ''
            if comp['used_latest_record']:
                answer += f"No production record for {comp['requested_date']} yet (the log ends {comp['date']}); using {comp['date']} ({comp['weekday']}). "
            if intent == Intent.OPERATIONS_OUTPUT:
                recorded = '; '.join(f"{x['stage'].lower()} {x['output']}" for x in comp['stages'] if x.get('output') is not None)
                packing = next((x for x in comp['stages'] if x['stage'] == 'PACKING' and x.get('output') is not None), None)
                answer += (f"Recorded output on {comp['date']} ({comp['weekday']}) by stage: {recorded} pieces. Stage outputs are not added together: the same piece passes every stage, so "
                           + (f"packing ({packing['output']}) is the closest thing to finished output. " if packing else 'packing is the closest thing to finished output. ')
                           + 'Against each stage\u2019s own previous eight same weekdays: ' + self.comparison_sentence(comp, None).split(': ', 1)[-1])
            else:
                answer += self.comparison_sentence(comp, None)
            if intent == Intent.OPERATIONS_DEVIATION or re.search(r'why|cause|reason', lowered):
                answer += ' The log has no cause, downtime, staffing or team fields; the reason has to come from the floor.'
            if re.search(r'total|overall|factory', lowered) and intent != Intent.OPERATIONS_OUTPUT:
                answer += ' Stage outputs are not added together: the same piece passes every stage, so packing is the closest thing to finished output.'
            return finish(answer, comp, rows, 'stage_comparison')
        if intent == Intent.OPERATIONS_OUTPUT:
            data, rows = self.tools.production_output(slots, now)
            if data['status'] != 'ok':
                answer = f"No production record for {data['date']} ({data['weekday']}). {data['note']}"
                if latest and target > latest:
                    answer += f" The latest record is {latest.isoformat()}."
            else:
                answer = f"Recorded output on {data['date']} ({data['weekday']}): " + '; '.join(f"{r['stage'].lower()} {r['pieces_completed']} pieces" for r in data['records']) + '. ' + data['note']
                if not slots.stage:
                    answer += ' Stage outputs are not added together: the same piece passes every stage, so packing is the closest thing to finished output.'
            return finish(answer, data, rows)
        # 5. one stage, one date (a figure the manager supplies for a day without a record is compared as an observation)
        if latest and target > latest and slots.observed_output is None:
            comp, rows = self.tools.stage_comparison(latest, now)
            answer = (f"No production record for {target.isoformat()} yet; the latest is {latest.isoformat()} ({comp['weekday']}). " + self.comparison_sentence(comp, slots.stage))
            return finish(answer, {'date': target.isoformat(), 'status': 'no_record_yet', 'latest_record': latest.isoformat(), 'latest_comparison': comp}, rows, 'stage_comparison')
        if slots.observed_output == 0 and not any(e.record['date'] == target.isoformat() for e in self.tools.rows('production_log.csv')):
            slots.observed_output = None   # a zero the planner invented for a missing day is not an observation
        baseline_defaulted = intent == Intent.OPERATIONS_NORMALITY and not slots.baseline
        slots.baseline = 'same_weekday'
        function = self.tools.normality if intent == Intent.OPERATIONS_NORMALITY else self.tools.deviation
        data, rows = function(slots, now)
        if baseline_defaulted:
            data['baseline_note'] = 'Compared with the previous eight same weekdays by default (Sundays closed); say "compare with last week" for another baseline.'
        comparison = data if intent == Intent.OPERATIONS_NORMALITY else data['comparison']
        if comparison.get('status') in ('below', 'within', 'above'):
            verdict = {'below': 'below its normal range', 'within': 'within its normal range (normal)', 'above': 'above its normal range'}[comparison['status']]
            lead = (f"{slots.stage.title()} on {comparison['date']}: {comparison['output']} pieces, {verdict}; the previous eight same weekdays ran {comparison['minimum']}\u2013{comparison['maximum']} (mean {comparison['mean']}), "
                    f"{abs(comparison['change_pct'])}% {'below' if comparison['change_pct'] < 0 else 'above'} the mean.")
            if comparison.get('user_observation') is not None and comparison.get('observation_source') == 'production_log.csv' and comparison['user_observation'] != comparison['output']:
                lead = f"The record shows {comparison['output']} pieces on {comparison['date']}, not {comparison['user_observation']}. " + lead
            elif hypothetical and comparison.get('observation_source') != 'production_log.csv':
                weekday = datetime.fromisoformat(comparison['date'] + 'T00:00:00').strftime('%A')
                lead = (f"{comparison['output']} pieces would be {verdict} for {slots.stage.lower()} on a {weekday}: the previous eight {weekday}s ran "
                        f"{comparison['minimum']}\u2013{comparison['maximum']} (mean {comparison['mean']}), so it would be {abs(comparison['change_pct'])}% {'below' if comparison['change_pct'] < 0 else 'above'} the mean. "
                        f"A figure you give me is compared as stated, not verified against the log.")
            if intent == Intent.OPERATIONS_DEVIATION:
                others = [r for r in data['facts'] if r['stage'] != slots.stage]
                upstream = STAGE_ORDER[STAGE_ORDER.index(slots.stage) - 1] if slots.stage in STAGE_ORDER and STAGE_ORDER.index(slots.stage) > 0 else None
                up = next((r for r in others if r['stage'] == upstream), None)
                lead += ' Same day, other stages: ' + ', '.join(f"{r['stage'].lower()} {r['pieces_completed']}" for r in others) + '.'
                if up:
                    lead += f" Upstream {upstream.lower()} fed {up['pieces_completed']} pieces that day."
                lead += ' ' + data['missing'] + ' ' + data['next_check']
        else:
            lead = f"Cannot judge {(slots.stage or '').lower()} on {comparison.get('date')}: {comparison.get('note', 'insufficient baseline or observation')}"
        answer = lead + '\nRecorded facts and labelled interpretation:\n' + json.dumps(data, ensure_ascii=False, indent=2)
        return finish(answer, data, rows)

    def baseline_answer(self, state, slots, now, latest):
        """'What baseline did you use?' after a production answer: the rule(s) in words, with the figures they produced."""
        saved = state.topics.get('production_window')
        if saved:
            period = {'start': date.fromisoformat(saved['start']), 'end': date.fromisoformat(saved['end']), 'label': saved.get('label', ''), 'capped': False}
            data, rows = self.tools.production_window(period, now, saved.get('stage'))
            parts = [f"Two baselines, both from production_log.csv, for {saved.get('label') or (saved['start'] + ' to ' + saved['end'])}:",
                     "1. Same-weekday band: for each day in the period, the previous eight records of that stage on the same weekday (Sundays are closed and never counted). "
                     "A day is \u201cbelow range\u201d when it is under the lowest of those eight; the shortfall is the day\u2019s output minus the mean of the eight, summed over the period.",
                     "2. Prior working-day mean: the stage\u2019s average over every working day before the period started; the shortfall is that average minus each day\u2019s output, summed."]
            for agg in data['summary']:
                if agg['working_days']:
                    parts.append(f"{agg['stage'].title()}: {agg['total_pieces']:,} pieces over {agg['working_days']} working days; {agg['shortfall_vs_same_weekday_mean']:,} short by baseline 1"
                                 + (f", {agg['shortfall_vs_prior_working_day_mean']:,} short by baseline 2 ({agg['prior_working_day_mean']}/day over the {agg['prior_working_days']} working days before the period)." if agg['prior_working_day_mean'] else '.'))
            parts.append('Both are descriptive comparisons, not control limits or targets; say \u201ccompare with last week\u201d for a different reference period.')
            return '\n'.join(parts), data, rows, 'production_window'
        stage = slots.stage
        target_text = slots.target_date or 'yesterday'
        try:
            target = parse_day(target_text, now) or (latest or now.date() - timedelta(days=1))
        except ValueError:
            target = latest or now.date() - timedelta(days=1)
        comp, rows = self.tools.stage_comparison(target, now)
        item = next((x for x in comp['stages'] if x['stage'] == stage), None) if stage else None
        answer = ("One baseline: the previous eight records of the same stage on the same weekday before the date asked about (Sundays closed and skipped). "
                  "The range is the lowest to the highest of those eight; a day is normal inside it, below range under it, above range over it; the percentage is against their mean.")
        if item and item.get('minimum') is not None:
            answer += (f" For {stage.title()} on {comp['date']}: {item['samples']} same-weekday records, range {item['minimum']}\u2013{item['maximum']}, mean {item['mean']}; "
                       f"the day\u2019s {item['output']} pieces is {item['status']} that range ({item['change_pct']}%).")
        answer += ' It is a descriptive comparison, not a control limit; say \u201ccompare with last week\u201d for another reference.'
        return answer, comp, rows, 'stage_comparison'

    @staticmethod
    def comparison_sentence(comp, stage):
        parts = []
        for x in comp['stages']:
            if x.get('status') in ('below', 'within', 'above'):
                parts.append(f"{x['stage'].lower()} {x['output']} ({x['status']} {x['minimum']}\u2013{x['maximum']}" + (f", {x['change_pct']:+.0f}%" if x['status'] != 'within' else '') + (f", {x['below_days_running']} working days below" if x.get('below_days_running', 0) >= 2 else '') + ')')
            else:
                parts.append(f"{x['stage'].lower()} no record")
        worst = comp.get('most_off')
        head = (f"{worst.title()} is the stage to worry about on {comp['date']}" if worst else f"No stage was outside its normal range on {comp['date']}")
        if stage and worst and stage != worst:
            head = f"{stage.title()} was {next(x['status'] for x in comp['stages'] if x['stage'] == stage)} its range; {worst.lower()} is the one below range"
        return head + ': ' + '; '.join(parts) + '. Each stage is compared with its own previous eight same weekdays.'

    def window_answer(self, data, stage, intent, lowered):
        s = data['period']
        head = f"Production {s['label']}" + (' (capped at the latest record)' if s['capped_to_latest_record'] else '') + ':\n'
        cols = [stage] if stage else STAGE_ORDER
        lines = ['| Date | ' + ' | '.join(c.title() for c in cols) + ' |', '| --- | ' + ' | '.join('---' for _ in cols) + ' |']
        rows = data['rows']
        wants_rows = re.search(r'record|rows?\b|behind|show|table|list|each day|every day|day by day', lowered)
        if len(rows) > 14 and not wants_rows:
            # a month is too long to tabulate unasked: keep the days outside their range, say what was left out
            rows = [r for r in rows if not r.get('closed') and any((r.get(c) or {}).get('status') in ('below', 'above') for c in cols)]
            head += f"({len(data['rows'])} days; the table keeps the {len(rows)} working days outside their range; ask for the records to see every day.)\n"
        for r in rows:
            if r.get('closed'):
                lines.append(f"| {r['date']} {r['weekday']} | " + ' | '.join('closed (Sunday)' for _ in cols) + ' |')
                continue
            cells = []
            for c in cols:
                v = r.get(c)
                cells.append('no record' if v is None else f"{v['pieces']}" + (f" ({v['status']} {v['band_min']}\u2013{v['band_max']})" if v.get('status') else ''))
            lines.append(f"| {r['date']} {r['weekday']} | " + ' | '.join(cells) + ' |')
        summary = []
        for agg in data['summary']:
            if agg['working_days'] == 0:
                continue
            if agg['days_below_band']:
                run = (f"{agg['stage'].title()}: below its same-weekday range on {agg['days_below_band']} of {agg['working_days']} working days"
                       + (f" (every day since {agg['first_below']})" if agg['every_working_day_below'] else f" ({agg['first_below']} to {agg['last_below']}"
                          + (f", consecutively since {agg['run_start']}" if agg.get('run_start') and agg['run_start'] != agg['first_below'] else '') + ')')
                       + f"; {agg['total_pieces']:,} pieces in total, about {agg['shortfall_vs_same_weekday_mean']:,} short of the same-weekday means"
                       + (f" and about {agg['shortfall_vs_prior_working_day_mean']:,} short of its {agg['prior_working_day_mean']}/day average over the {agg['prior_working_days']} working days before" if agg['prior_working_day_mean'] else '') + '.')
            else:
                run = f"{agg['stage'].title()}: inside its range every working day ({agg['total_pieces']:,} pieces; range before the period {agg['range_before'][0]}\u2013{agg['range_before'][1]})." if agg['range_before'] else f"{agg['stage'].title()}: inside its range."
            if re.search(r'average|mean|per day|a day|daily', lowered) and agg.get('mean_per_working_day') is not None:
                run += (f" Average {agg['mean_per_working_day']} pieces per working day over {agg['working_days']} working days"
                        + (f" ({agg['sundays_closed']} Sundays closed)" if agg.get('sundays_closed') else '') + '.')
                if agg.get('mean_before_run') is not None:
                    run += (f" That average hides the drop: {agg['mean_before_run']}/day before {agg['run_start']}, "
                            f"{agg['mean_from_run']}/day from {agg['run_start']} on ({agg['run_days']} consecutive working days below range).")
            summary.append(run)
        answer = head + '\n'.join(lines) + '\n' + ' '.join(summary)
        if re.search(r'why|cause|reason|responsible|team', lowered):
            answer += ' ' + data['limits'].split('. ', 1)[-1] + ' Upstream stages inside their range make an input shortage unlikely; the cause has to be checked on the floor.'
        else:
            answer += ' ' + data['limits']
        return answer

    def hypothesis_note(self, workshop, calls):
        calls.append(ToolCall(name='list_workshops', arguments={'workshop_id': workshop['workshop_id']}, result={'workshop': workshop}))
        return (f"\nOn the {workshop['name']} hypothesis: the workshop table lists {workshop['workshop_id']} {workshop['name']} as {workshop['status']}"
                + (f" (\u201c{workshop['notes']}\u201d)" if workshop.get('notes') else '') +
                ", with no suspension date and no field linking any workshop to the factory\u2019s own stage output, so the data cannot confirm or rule out a link. "
                "Worth checking on the floor: did this workshop do assembly work for us, and when exactly was it suspended?")

    def lead_time_for_size(self, slots: Slots, state: DialogState, result: Classification, now: datetime, calls: list[ToolCall], evidence: list[Evidence]) -> ChatResponse:
        """Typical lead time for an order size: the completed orders of that product near that size, and the lead-time model."""
        from .prediction.aft import LeadTimeModel
        qty = int(slots.quantity)
        product = (slots.product or '').lower().rstrip('s')
        done = [e for e in self.tools.rows('orders.csv') if e.record['status'] == 'COMPLETE' and e.record.get('completed_date')]
        same = [e for e in done if (not product or product[:5] in e.record['product'].lower()) and 0.7 * qty <= int(e.record['pieces']) <= 1.3 * qty]
        days = sorted((datetime.fromisoformat(e.record['completed_date']).date() - datetime.fromisoformat(e.record['order_date']).date()).days for e in same)
        model = LeadTimeModel()
        typical = round(model.typical_lead_days(float(qty)), 1)
        stats = {'quantity': qty, 'product': slots.product, 'similar_completed_orders': [e.record['order_id'] for e in same], 'lead_days': days,
                 'median_days': days[len(days) // 2] if days else None, 'min_days': days[0] if days else None, 'max_days': days[-1] if days else None, 'model_typical_lead_days': typical}
        calls.append(ToolCall(name='predict_order_delay', arguments={'quantity': qty, 'product': slots.product}, result=stats))
        evidence.extend(same)
        label = f"{qty:,}-piece {product} orders" if product else f'{qty:,}-piece orders'
        if days:
            answer = (f"{len(same)} completed {label} within 30% of that size took {days[0]}\u2013{days[-1]} calendar days from order to completion (median {stats['median_days']}): "
                      + ', '.join(f"{e.record['order_id']} {e.record['pieces']} pcs {d} d" for e, d in zip(same, [(datetime.fromisoformat(e.record['completed_date']).date() - datetime.fromisoformat(e.record['order_date']).date()).days for e in same]))
                      + f". The lead-time model's typical lead time for {qty:,} pieces is {typical} days. Past durations, not a promise for a new order; ask \u201ccan we take \u2026 by \u2026\u201d for the queue-based estimate.")
        else:
            answer = f"No completed {label} close to that size in the records. The lead-time model's typical lead time for {qty:,} pieces is {typical} days; ask \u201ccan we take \u2026 by \u2026\u201d for the queue-based estimate."
        return self.response(state, result, now, answer, calls, evidence)

    def saved_notes(self, order_id: str) -> list[dict]:
        """Internal notes already saved for an order, from the shared records when present, else the local store."""
        try:
            if getattr(self, 'order_records', None):
                return [n for n in self.order_records.list(order_id) if n.get('kind') == 'note']
            return self.store.actions_for(order_id, ('note',))
        except Exception:
            return []

    def customers_named(self, message: str) -> list[str]:
        """Every known customer named in the message (spacing and small typos tolerated), in order of appearance."""
        lowered = message.casefold()
        found = []
        for c in known_customers(self.tools):
            key = re.sub(r'[^a-z0-9]', '', c.casefold())
            compact = re.sub(r'[^a-z0-9]', '', lowered)
            pos = compact.find(key)
            if pos < 0:
                import difflib
                for i in range(0, max(1, len(compact) - len(key) + 3)):
                    if difflib.SequenceMatcher(None, compact[i:i + len(key)], key).ratio() >= 0.88:
                        pos = i; break
            if pos >= 0:
                found.append((pos, c))
        return [c for _, c in sorted(found)]

    def compare_customers(self, customers: list[str], now: datetime, message: str):
        """Two customers side by side on their active orders: count, overdue, idle, pieces; a stated verdict."""
        today = now.date()
        rows_all = [e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS' and e.record['customer'] in customers]
        facts = {}
        for c in customers:
            rows = [e for e in rows_all if e.record['customer'] == c]
            overdue = [e for e in rows if e.record['due_date'] < today.isoformat()]
            idle = [e for e in rows if (today - datetime.fromisoformat(e.record['last_activity_date'] + 'T00:00:00').date()).days >= 5]
            facts[c] = {'active': len(rows), 'overdue': len(overdue), 'overdue_ids': [e.record['order_id'] for e in overdue],
                        'idle_5d': len(idle), 'idle_ids': [e.record['order_id'] for e in idle], 'pieces': sum(int(e.record['pieces']) for e in rows),
                        'worst_overdue_days': max([(today - datetime.fromisoformat(e.record['due_date'] + 'T00:00:00').date()).days for e in overdue], default=0)}
        stale = bool(re.search(r'stale|idle|quiet|activity|update|movement|reliable', message.casefold()))
        key = (lambda c: (facts[c]['idle_5d'] / max(facts[c]['active'], 1), facts[c]['overdue'])) if stale else (lambda c: (facts[c]['overdue'], facts[c]['worst_overdue_days'], facts[c]['idle_5d']))
        ranked = sorted(customers, key=key, reverse=True)
        worse = ranked[0]
        other = ranked[1] if len(ranked) > 1 else worse
        tie = len(ranked) > 1 and key(worse) == key(other)
        lines = [f"{c}: {f['active']} active orders ({f['pieces']:,} pieces); {f['overdue']} overdue" + (f" ({', '.join(f['overdue_ids'])}; worst {f['worst_overdue_days']} days)" if f['overdue'] else '')
                 + f"; {f['idle_5d']} with no recorded activity for 5+ days" + (f" ({', '.join(f['idle_ids'])})" if f['idle_5d'] else '') + '.' for c, f in facts.items()]
        if tie:
            verdict = f"Neither looks worse on {'stale updates' if stale else 'overdue orders'}: the counts are equal. Overdue first, then idle, is how the orders are ranked."
        elif stale and len(customers) > 2:
            verdict = (f"{worse} has the greater share of in-progress orders without recent recorded activity ({facts[worse]['idle_5d']} of {facts[worse]['active']}); next "
                       + ', '.join(f"{c} ({facts[c]['idle_5d']} of {facts[c]['active']})" for c in ranked[1:4]) + '. Every customer with active orders is included.')
        elif stale:
            verdict = f"{worse} has the greater share of in-progress orders without recent recorded activity ({facts[worse]['idle_5d']} of {facts[worse]['active']} vs {facts[other]['idle_5d']} of {facts[other]['active']})."
        else:
            verdict = f"{worse} needs attention first: {facts[worse]['overdue']} overdue vs {facts[other]['overdue']}" + (f", worst {facts[worse]['worst_overdue_days']} days late" if facts[worse]['overdue'] else '') + '.'
        call = ToolCall(name='compare_orders', arguments={'customers': customers, 'as_of': today.isoformat()}, result={'customers': facts, 'verdict': verdict})
        return '\n'.join(lines) + '\n' + verdict, call, rows_all

    def known_order_numbers(self) -> set[int]:
        return {int(e.record['order_id'][4:]) for e in self.tools.rows('orders.csv') if e.record['order_id'][4:].isdigit()}

    def known_products(self) -> set[str]:
        return {e.record['product'].split()[0] for e in self.tools.rows('orders.csv')} | {e.record['product'] for e in self.tools.rows('orders.csv')}

    def compare_pace(self, ids: list[str], now: datetime):
        """Required daily completion rate for two orders: pieces still to make (full quantity, no WIP data) over the working
        days left to the due date (Sundays closed; today counts), with the queue's best-case finish beside it."""
        from .services.queue_engine import working_days_inclusive
        rows = [self.tools.refresh_order(i) for i in ids]
        facts = []
        for e in rows:
            r = e.record
            due = datetime.fromisoformat(r['due_date'] + 'T00:00:00').date()
            days = working_days_inclusive(now.date(), due) if due >= now.date() else 0
            risk = self.tools.assess_risk(e, now) if r['status'] == 'IN_PROGRESS' else {}
            facts.append({'order_id': r['order_id'], 'pieces': int(r['pieces']), 'stage': r['current_stage'], 'due_date': r['due_date'], 'working_days_left': days,
                          'pieces_per_working_day_needed': round(int(r['pieces']) / days) if days else None, 'best_case_finish': risk.get('best_date'), 'risk_level': risk.get('risk_level'),
                          'stages_left': (len(STAGE_ORDER) - STAGE_ORDER.index(r['current_stage'])) if r['current_stage'] in STAGE_ORDER else None})
        def pressure(f): return (0 if f['working_days_left'] == 0 else 1, -(f['pieces_per_working_day_needed'] or 10 ** 9), f['due_date'])
        tighter = min(facts, key=pressure)
        lines = []
        for f in facts:
            lines.append(f"{f['order_id']}: {f['pieces']:,} pieces at {f['stage'].lower()} ({f['stages_left']} stages left), due {f['due_date']}, "
                         + (f"{f['working_days_left']} working day{'s' if f['working_days_left'] != 1 else ''} left → about {f['pieces_per_working_day_needed']:,} pieces per working day needed" if f['working_days_left'] else 'due date passed, so no daily rate reaches it')
                         + (f"; queue best-case finish {f['best_case_finish']} ({f['risk_level']})" if f['best_case_finish'] else '') + '.')
        verdict = (f"{tighter['order_id']} needs the tougher pace" + (': its due date has passed.' if tighter['working_days_left'] == 0 else
                   f": {tighter['pieces_per_working_day_needed']:,} pieces per working day against " + ', '.join(f"{f['pieces_per_working_day_needed']:,} for {f['order_id']}" for f in facts if f is not tighter) + '.'))
        text = '\n'.join(lines) + '\n' + verdict + ' Remaining quantity is the full order because per-order WIP is not recorded; the rate compares pressure, not a schedule.'
        return text, ToolCall(name='compare_orders', arguments={'order_ids': ids, 'criterion': 'required_daily_pace'}, result={'orders': facts, 'tighter': tighter['order_id']}), rows

    def customer_summary(self, customer: str, matches: list, state: DialogState, result: Classification, now: datetime, calls: list, evidence: list) -> ChatResponse:
        """'Anything on TrendCart's orders I need to act on?': every active order of the customer with its risk, acted-on ones first."""
        risks = {e.record['order_id']: self.tools.assess_risk(e, now) for e in matches if e.record['status'] == 'IN_PROGRESS'}
        rank = {'overdue': 0, 'high': 1, 'medium': 2, 'unknown': 3, 'low': 4}
        ordered = sorted(risks, key=lambda i: (rank.get(risks[i]['risk_level'], 5), risks[i]['days_to_due'], i))
        recs = {e.record['order_id']: e.record for e in matches}
        act, watch = [], []
        for i in ordered:
            r, k = recs[i], risks[i]
            days = k['days_to_due']
            when = f"{-days} d overdue" if days < 0 else 'due today' if days == 0 else f"due in {days} d"
            line = f"{i} ({r['pieces']} {r['product']}, {r['current_stage'].lower()}, {when}, idle {k['idle_days']} d" + (', stalled' if k.get('stalled') else '') + f", {k['risk_level']})"
            (act if k['risk_level'] in ('overdue', 'high') or k.get('stalled') or k['idle_days'] >= 5 else watch).append(line)
        text = (f"{customer}: {len(risks)} active orders as of {now.date().isoformat()}. "
                + (f"Act today on {len(act)}: " + '; '.join(act) + '.' if act else 'Nothing needs action today.')
                + (f" Watch: " + '; '.join(watch) + '.' if watch else '')
                + ' Overdue and best-case-late orders need a new date or an expedite decision; idle ones a chase. Say an order ID for its detail or draft.')
        calls.append(ToolCall(name='assess_order_risk', arguments={'customer': customer, 'order_ids': ordered}, result={'risks': {i: {'risk_level': risks[i]['risk_level'], 'days_to_due': risks[i]['days_to_due'], 'idle_days': risks[i]['idle_days']} for i in ordered}}))
        evidence.extend(matches)
        state.comparison_orders = []
        state.active_order = None
        state.active_customer = customer
        state.last_order_ids = ordered
        return self.response(state, result, now, text, calls, evidence)

    @staticmethod
    def commitment_lead(slots: Slots, data: dict, now: datetime) -> str:
        """One sentence a manager can act on, ahead of the labelled forecast."""
        q = data.get('queue_projection') or {}
        best, exp = q.get('best_case') or {}, q.get('expected_case') or {}
        verdict = data.get('preliminary') or data.get('verdict')
        text = f"{slots.quantity:,} {slots.product.lower()} by {data['due_date']} ({'ready at the factory' if slots.delivery_point == 'factory' else 'delivered to the customer'}): {verdict}. "
        text += f"{data['available_workdays']} working day{'s' if data['available_workdays'] != 1 else ''} available"
        if best.get('finish_date'):
            text += f"; the shared queue puts the finish at {best['finish_date']} best case ({best['working_days']} working days, {q.get('orders_ahead')} active orders ahead)"
            if exp.get('finish_date') and exp['finish_date'] != best['finish_date']:
                text += f" and {exp['finish_date']} if new orders keep arriving"
        text += '.'
        aft = data.get('historical_lead_time_model') or {}
        if isinstance(aft, dict) and aft.get('p_on_time') is not None:
            text += f" Historically, orders of this size finished within {aft['promised_lead_days']} days {aft['p_on_time']:.0%} of the time (typical {aft['typical_lead_days']} days)."
        wc = data.get('worst_case_serial_backlog') or {}
        if wc.get('limiting_stage'):
            text += f" Limiting stage in the serial worst case: {wc['limiting_stage'].lower()}."
        return text

    def commitment_comparison(self, responses: list[ChatResponse], state: DialogState, now: datetime) -> ChatResponse:
        """Two or more new-order options side by side: available days, best-case finish, slack, verdict, and which is safer."""
        opts = []
        for r in responses:
            call = next((c for c in r.tool_calls if c.name == 'estimate_capacity'), None)
            if not call: continue
            d = call.result; a = call.arguments
            q = d.get('queue_projection') or {}; bc = q.get('best_case') or {}
            slack = (d.get('available_workdays') or 0) - (bc.get('working_days') or 0) if bc.get('working_days') else None
            opts.append({'option': f"{a.get('quantity'):,} {str(a.get('product', '')).lower()} by {d['due_date']}", 'available_workdays': d.get('available_workdays'),
                         'best_case_finish': bc.get('finish_date'), 'best_case_working_days': bc.get('working_days'), 'slack_working_days': slack, 'verdict': d.get('preliminary') or d.get('verdict')})
        if len(opts) < 2:
            return responses[0]
        rank = {'likely': 0, 'tight': 1, 'unlikely': 2}
        safer = min(opts, key=lambda o: (rank.get(str(o['verdict']).split(' ')[0].rstrip(':'), 3), -(o['slack_working_days'] if o['slack_working_days'] is not None else -10 ** 6)))
        table = '| Option | Working days available | Best-case finish | Slack (working days) | Verdict |\n| --- | --- | --- | --- | --- |\n' + '\n'.join(
            f"| {o['option']} | {o['available_workdays']} | {o['best_case_finish'] or 'n/a'} ({o['best_case_working_days']} wd) | {o['slack_working_days'] if o['slack_working_days'] is not None else 'n/a'} | {o['verdict']} |" for o in opts)
        both_unlikely = all(str(o['verdict']).startswith('unlikely') for o in opts)
        verdict = (f"Safer: {safer['option']} — the smaller shortfall ({safer['slack_working_days']} working days of slack), but neither is met on current orders without a priority decision; promise neither date unconditionally."
                   if both_unlikely else f"Safer: {safer['option']} ({safer['verdict']}, slack {safer['slack_working_days']} working days).")
        text = 'Side by side (same queue, same assumptions):\n' + table + '\n' + verdict
        call = ToolCall(name='estimate_capacity', arguments={'compare': [o['option'] for o in opts]}, result={'options': opts, 'safer': safer['option']})
        return ChatResponse(answer=text, intent=Intent.ORDER_COMMITMENT, slots=state.slots, confidence=responses[0].confidence, state=state, tool_calls=[call], evidence=[],
                            source_details=responses[0].source_details, business_date=now.date().isoformat())

    def max_quantity_by(self, slots: Slots, now: datetime):
        """Largest quantity whose best-case queue finish is on or before the due date (bisection on the queue simulation)."""
        due = resolve_date(slots.due_date, now)
        def fits(q: int):
            data, rows = self.tools.capacity(slots.model_copy(update={'quantity': q}), now)
            bc = (data.get('queue_projection') or {}).get('best_case') or {}
            return bool(bc.get('finish_date')) and bc['finish_date'] <= due.isoformat(), data, rows
        ok, probe, rows = fits(1)
        if not ok:
            return 0, probe, rows
        lo, hi = 1, 50000
        while lo < hi:
            mid = (lo + hi + 1) // 2
            good, d, r = fits(mid)
            if good:
                lo, probe, rows = mid, d, r
            else:
                hi = mid - 1
        return lo, probe, rows

    def stage_focus(self, now: datetime) -> dict | None:
        """Which single stage to focus on today: the stage below its range, weighed with where the at-risk orders sit."""
        active = [e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS']
        at_risk = {}
        for e in active:
            k = self.tools.assess_risk(e, now)
            if k['risk_level'] in ('overdue', 'high'):
                at_risk[e.record['order_id']] = e.record['current_stage']
        counts = {s: sum(1 for st in at_risk.values() if st == s) for s in STAGE_ORDER}
        drop = None
        try:
            data, _ = self.tools.find_anomalies(Slots(window_days=20), now)
            drop = next((f for f in data['findings'] if f['kind'] == 'stage_drop'), None)
        except Exception:
            drop = None
        drop_stage = (drop or {}).get('entity')
        if drop_stage in STAGE_ORDER:
            downstream = sum(counts[s] for s in STAGE_ORDER[STAGE_ORDER.index(drop_stage):])
            why = f"{drop_stage.lower()} is the stage below its normal range ({drop['title'].split('(')[-1].rstrip(')')}) and {downstream} of the {len(at_risk)} overdue or high-risk orders are at or after it"
            return {'stage': drop_stage, 'why': why, 'at_risk_by_stage': counts}
        if at_risk:
            best = max(counts, key=lambda s: counts[s])
            return {'stage': best, 'why': f"{counts[best]} of the {len(at_risk)} overdue or high-risk orders are waiting at {best.lower()}", 'at_risk_by_stage': counts}
        return None

    def describe_candidates(self, message: str, now: datetime):
        """'the order that was late yesterday', 'the overdue order', 'the stalled order' -> the real candidates and a label."""
        lowered = message.casefold()
        today = now.date()
        active = [e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS']
        if re.search(r'\b(late|overdue|overdued|past due|missed)\b', lowered):
            rows = sorted([e for e in active if e.record['due_date'] < today.isoformat()], key=lambda e: e.record['due_date'])
            m = re.search(r'(?:more than|over|>|>=|at least|beyond)\s*(\d+)\s*(days?|d\b|hours?|h\b)', lowered) or re.search(r'(?:overdue|overdued|late|past due)\w*\s*(?:by|for)?\s*(\d+)\s*(days?|d\b|hours?|h\b)', lowered)
            if m:
                threshold = int(m[1]) // 24 if m[2].startswith('h') else int(m[1])
                rows = [e for e in rows if (today - datetime.fromisoformat(e.record['due_date'] + 'T00:00:00').date()).days > threshold]
                return (f'{len(rows)} active orders are more than {threshold} days overdue as of {today.isoformat()}', rows) if rows else (f'no active order is more than {threshold} days overdue', [])
            return (f'{len(rows)} active orders are overdue as of {today.isoformat()}', rows) if rows else None
        stage = re.search(r'\b(knitting|assembly|washing|packing)\b', lowered)
        if stage and re.search(r'\b(at|in|stuck|pending|phase|stage|queue|waiting)\b', lowered):
            rows = sorted([e for e in active if e.record['current_stage'] == stage[1].upper()], key=lambda e: e.record['due_date'])
            return (f'{len(rows)} active orders are at {stage[1]}', rows) if rows else (f'no active order is at {stage[1]}', [])
        if re.search(r'\b(largest|biggest|main|top|most important) (customer|client|account)\b|customer with (the )?(largest|biggest|most|highest)|(largest|biggest|most) (open|outstanding|unfilled|active)? ?(order )?(volume|pieces|backlog)', lowered):
            counts: dict[str, list] = {}
            for e in active: counts.setdefault(e.record['customer'], []).append(e)
            by_pieces = bool(re.search(r'pieces|volume|backlog|unfilled|outstanding', lowered))
            size = (lambda v: sum(int(e.record['pieces']) for e in v)) if by_pieces else len
            best = max(size(v) for v in counts.values())
            leaders = sorted(c for c, v in counts.items() if size(v) == best)
            rows = sorted([e for c in leaders for e in counts[c]], key=lambda e: (e.record['customer'], e.record['due_date']))
            label = ' and '.join(leaders) + (f' {"each have" if len(leaders) > 1 else "has"} the most active pieces outstanding ({best:,} pieces in {len(rows)} orders)' if by_pieces
                                              else f' {"each have" if len(leaders) > 1 else "has"} the most active orders ({best})')
            return (label, rows)
        products = {e.record['product'] for e in self.tools.rows('orders.csv')}
        words = {p.lower().split()[0]: p for p in products} | {'scarves': 'Scarf', 'beanies': 'Beanie', 'vests': 'Vest', 'hoodies': 'Hoodie', 'cardigans': 'Cardigan', 'polos': 'Polo shirt', 'sweaters': 'Crewneck sweater', 'crewnecks': 'Crewneck sweater'}
        categories = {'tops': 'TOPS', 'top': 'TOPS', 'accessories': 'ACCESSORIES', 'accessory': 'ACCESSORIES'}
        qty = re.search(r'\b(\d{2,5})\s*(?:-?\s*(?:piece|pieces|pcs|pc))?\s+(' + '|'.join(sorted(set(words) | set(categories), key=len, reverse=True)) + r')\b', lowered)
        prod = re.search(r'\b(' + '|'.join(sorted(words, key=len, reverse=True)) + r')\b', lowered)
        if qty or prod:
            n = int(qty[1]) if qty else None
            word = (qty[2] if qty else prod[1])
            if word in categories:
                rows = [e for e in active if e.record['category'] == categories[word] and (n is None or int(e.record['pieces']) == n)]
                label = f"{len(rows)} active {categories[word].lower()} orders" + (f" of {n} pieces" if n else '')
            else:
                rows = [e for e in active if e.record['product'] == words[word] and (n is None or int(e.record['pieces']) == n)]
                label = f"{len(rows)} active {words[word].lower()} orders" + (f" of {n} pieces" if n else '')
            rows = sorted(rows, key=lambda e: e.record['due_date'])
            if rows:
                return (label, rows)
            if n is not None:
                have = sorted([e for e in active if (e.record['category'] == categories[word] if word in categories else e.record['product'] == words[word])], key=lambda e: e.record['due_date'])
                name = categories[word].lower() if word in categories else words[word].lower()
                return (f"no active {name} order of {n} pieces; active {name} orders: " + (', '.join(f"{e.record['order_id']} ({e.record['pieces']} pieces, due {e.record['due_date']})" for e in have) or 'none'), [])
        bare = re.fullmatch(r'\W*(?:show me |what is |the |status of |status for |order )*(\d{1,3})\W*(?:status|is in which production phase now|stage|progress)?\W*', lowered)
        if bare and int(bare[1]) in self.known_order_numbers():
            rows = [e for e in self.tools.rows('orders.csv') if e.record['order_id'] == f'ORD-{int(bare[1]):03d}']
            return (f'reading {bare[1]} as ORD-{int(bare[1]):03d}', rows)
        if re.search(r'\b(stalled|stuck|not moving|idle|quiet|no activity)\b', lowered):
            rows = sorted([e for e in active if (today - datetime.fromisoformat(e.record['last_activity_date'] + 'T00:00:00').date()).days >= 5], key=lambda e: e.record['last_activity_date'])
            return (f'{len(rows)} active orders have had no recorded activity for 5 days or more', rows) if rows else None
        if re.search(r'\bdue today\b', lowered):
            rows = [e for e in active if e.record['due_date'] == today.isoformat()]
            return (f'{len(rows)} active orders are due today', rows) if rows else None
        return None

    @staticmethod
    def candidate_facts(record, now: datetime) -> dict:
        """The derived figures a candidate hint quotes (days to/past due, idle days), so they are traceable tool output."""
        today = now.date()
        due = datetime.fromisoformat(record['due_date'] + 'T00:00:00').date()
        idle = (today - datetime.fromisoformat(record['last_activity_date'] + 'T00:00:00').date()).days
        return {'order_id': record['order_id'], 'customer': record['customer'], 'pieces': record['pieces'], 'product': record['product'],
                'current_stage': record['current_stage'], 'due_date': record['due_date'], 'days_to_due': (due - today).days, 'idle_days': idle}

    @staticmethod
    def candidate_hint(record, now: datetime) -> str:
        f = WorkflowEngine.candidate_facts(record, now)
        days, idle = f['days_to_due'], f['idle_days']
        when = f"{-days} d overdue" if days < 0 else 'due today' if days == 0 else f"due in {days} d"
        return f"{record['order_id']} ({record['customer']}, {record['pieces']} {record['product']}, {record['current_stage'].lower()}, {when}" + (f", idle {idle} d" if idle >= 5 else '') + ')'

    def candidate_call(self, rows, now: datetime, **arguments) -> ToolCall:
        return ToolCall(name='search_orders', arguments=arguments, result={'candidates': [self.candidate_facts(e.record, now) for e in rows]})

    # ------------------------------------------------------------------ grounding
    FOREIGN_STAGES = {'cutting': 'cutting', 'cut': 'cutting', 'sewing': 'sewing', 'sew': 'sewing', 'embroidery': 'embroidery', 'embroidered': 'embroidery', 'embroidry': 'embroidery', 'inspection': 'inspection',
                      'dyeing': 'dyeing', 'printing': 'printing', 'pressing': 'pressing', 'ironing': 'ironing', 'quality control': 'quality control', 'qc': 'quality control',
                      'colour matching': 'colour matching', 'color matching': 'colour matching', 'sewin': 'sewing', 'cuting': 'cutting', 'inspecton': 'inspection', 'embroidry': 'embroidery'}
    PRODUCT_STOP = {'active', 'overdue', 'overdued', 'late', 'open', 'new', 'these', 'those', 'this', 'that', 'the', 'all', 'which', 'what', 'my', 'our', 'your', 'two', 'three', 'both', 'other', 'similar',
                    'past', 'completed', 'complete', 'finished', 'stale', 'idle', 'quiet', 'risky', 'urgent', 'pending', 'current', 'remaining', 'existing', 'running', 'many', 'more', 'most', 'few',
                    'several', 'some', 'any', 'no', 'each', 'every', 'first', 'last', 'next', 'previous', 'customer', 'customers', 'their', 'its', 'his', 'her', 'about', 'for', 'of', 'on', 'in', 'from',
                    'with', 'and', 'or', 'between', 'into', 'per', 'top', 'same', 'such', 'matching', 'affected', 'delayed', 'problem', 'priority', 'production', 'progress', 'in-progress', 'hidden',
                    'risk', 'high-risk', 'due', 'chase', 'draft', 'send', 'compare', 'show', 'list', 'rank', 'check', 'hoodie', 'hoodies', 'cardigan', 'cardigans', 'scarf', 'scarves', 'vest', 'vests',
                    'beanie', 'beanies', 'polo', 'polos', 'sweater', 'sweaters', 'crewneck', 'crewnecks', 'tops', 'accessories', 'accessory', 'knitwear', 'workshop', 'department', 'summary', 'placed',
                    'unfilled', 'outstanding', 'large', 'largest', 'biggest', 'small', 'smaller', 'bigger', 'older', 'oldest', 'newer', 'recent', 'future', 'today', 'tomorrow', 'yesterday', 'week',
                    'month', 'day', 'days', 'queue', 'critical', 'important', 'key', 'main', 'major', 'minor', 'relevant', 'related', 'said', 'mentioned', 'discussed', 'listed', 'shown', 'above',
                    'below', 'following', 'remaining', 'planned', 'scheduled', 'ready', 'export', 'domestic', 'local', 'overseas', 'uniform', 'vip', 'sample', 'trial', 'bulk', 'repeat', 'rush', 'wrong', 'right'}
    GARMENT_WORDS = {'jacket', 'uniform', 'outerwear', 'mitten', 'tunic', 'shirt', 'trouser', 'pant', 'dress', 'skirt', 'coat', 'glove', 'sock', 'blanket', 'towel', 'cap', 'hat', 'jean',
                     'suit', 'blouse', 'legging', 'short', 'tee', 't-shirt', 'sweatshirt', 'pullover', 'jumper', 'blazer', 'parka', 'anorak', 'gilet', 'shawl', 'poncho', 'cape', 'romper', 'onesie',
                     'bodysuit', 'swimwear', 'underwear', 'bra', 'lingerie', 'pyjama', 'pajama', 'robe', 'apron', 'bag', 'tote', 'backpack', 'belt', 'tie', 'scarve', 'knitwear', 'denim', 'linen', 'silk'}
    ORDER_TAGS = {'export', 'domestic', 'local', 'overseas', 'uniform', 'vip', 'sample', 'trial', 'bulk', 'repeat', 'rush'}   # words that look like an order type the records do not hold

    def known_product_words(self) -> set[str]:
        words = set()
        for p in {e.record['product'] for e in self.tools.rows('orders.csv')}:
            for w in p.lower().split():
                words.add(w); words.add(w + 's'); words.add(w + 'es')
            words.add(p.lower()); words.add(p.lower() + 's')
        words |= {'scarves', 'tops', 'top', 'accessories', 'accessory', 'knitwear', 'garments', 'garment', 'pieces', 'piece'}
        return words

    def foreign_product(self, message: str, slots: Slots) -> str | None:
        """A product word the records do not hold ("jacket orders", product='mittens'); None when every product word is on file."""
        import difflib
        known = self.known_product_words()
        def is_known(w: str) -> bool:
            w = w.lower().strip()
            if w in known or w.rstrip('s') in known or w in self.PRODUCT_STOP: return True
            return any(difflib.SequenceMatcher(None, w.rstrip('s'), k.rstrip('s')).ratio() >= 0.85 for k in known if len(k) >= 4)
        customers = ' '.join(known_customers(self.tools)).lower().split()
        candidates = []
        if slots.product and not is_known(slots.product) and slots.product.lower() not in self.ORDER_TAGS:
            candidates.append(slots.product.lower())
        for m in re.finditer(r"\b([a-z][a-z\-]{3,})\s+(?:orders?|jobs?|batch(?:es)?|lines?|styles?)\b", message.casefold()):
            w = m.group(1)
            if w in customers or is_known(w) or w in self.ORDER_TAGS or w in self.FOREIGN_STAGES: continue
            if w.rstrip('s') in self.GARMENT_WORDS or w in self.GARMENT_WORDS:
                candidates.append(w)
        return candidates[0] if candidates else None

    def foreign_tag(self, message: str, slots: Slots) -> str | None:
        lowered = message.casefold()
        for tag in self.ORDER_TAGS:
            if re.search(r'\b' + tag + r'\b\s+(?:orders?|jobs?|customers?|batch(?:es)?)', lowered) or (slots.product or '').lower() == tag:
                return tag
        return None

    def foreign_stage(self, message: str) -> str | None:
        lowered = message.casefold()
        hits = []
        for word, name in self.FOREIGN_STAGES.items():
            m = re.search(r'\b' + re.escape(word) + r'\b', lowered)
            if m: hits.append((m.start(), name))
        return min(hits)[1] if hits else None

    def foreign_order_numbers(self, message: str, explicit_ids: list[str]) -> list[str]:
        """Order references that are not on file: ORD-244, "order 218", "237 status?", spoken digits already normalised."""
        from .services.order_refs import WORDNUM, words_to_digits
        known = self.known_order_numbers()
        found = [i for i in explicit_ids if int(i[4:]) not in known]
        lowered = message.casefold()
        def add(n: int):
            if 0 < n < 1000 and n not in known and f'ORD-{n:03d}' not in found: found.append(f'ORD-{n:03d}')
        for m in re.finditer(r'\b(?:ord|orders?)\s*(?:number|no\.?|id)?\s*#?\s*((?:\d{1,4})(?:\s*(?:,|and|&|or|vs\.?|versus)\s*\d{1,4})*)\b', lowered):
            for n in re.findall(r'\d{1,4}', m.group(1)): add(int(n))
        for m in re.finditer(r'\b(?:ord|order)\s*(?:number|no\.?|id)?\s+((?:' + WORDNUM + r')(?:[\s\-]+(?:' + WORDNUM + r')){0,6})\b', lowered):
            d = words_to_digits(m.group(1))
            if d.isdigit(): add(int(d))
        for m in re.finditer(r'(?<![\w-])(\d{3})(\s*(?:vs\.?|versus|v\.|or|and)\s*)(\d{3})(?![\w-])', lowered):
            if int(m.group(1)) not in known and int(m.group(3)) not in known: add(int(m.group(1))); add(int(m.group(3)))
        if re.search(r'\b(status|stuck|chase|remind|expedite|note|phase|stage|moved|moving|progress|where)\b', lowered) and not re.search(r'\b(output|pieces|pcs|did|cleared|hit|normal|range|took|take|lead time)\b', lowered):
            for m in re.finditer(r'(?<![\w\-,.])(\d{3})(?![\w\-,.%])(?!\s*(?:pieces|pcs|piece|%|days|hours|hrs|on \d|' + '|'.join(sorted(self.known_product_words(), key=len, reverse=True)) + r'))', lowered):
                if int(m.group(1)) > max(known): add(int(m.group(1)))
        bare = re.fullmatch(r'\W*(?:show me |what is |the |status of |status for )*(\d{3})\W*(?:status|in which production phase now|stage|progress|at where)?\W*', message.casefold())
        if bare and int(bare[1]) not in known and f'ORD-{int(bare[1]):03d}' not in found:
            found.append(f'ORD-{int(bare[1]):03d}')
        return found

    def foreign_workshop(self, message: str, slots: Slots) -> str | None:
        on_file = {e.record['workshop_id'].upper() for e in self.tools.rows('workshops.csv')}
        text = message.upper() + ' ' + (slots.recipient or '').upper()
        for m in re.finditer(r'\bW(\d{1,2})\b', text):
            if f'W{int(m.group(1))}' not in on_file:
                return f'W{int(m.group(1))}'
        return None

    def foreign_customer(self, message: str, slots: Slots) -> str | None:
        """A customer the planner or the message names that is not on file (fuzzy match tolerated)."""
        if slots.customer and not detect_customer(slots.customer, self.tools) and slots.customer.casefold() not in message.casefold().replace('’', "'"):
            return slots.customer
        if slots.customer and not detect_customer(message, self.tools) and not detect_customer(slots.customer, self.tools):
            return slots.customer
        if not detect_customer(message, self.tools):
            names = [m.group(0) for m in re.finditer(r"\b([A-Z][a-z]{2,}(?:\s+(?:&\s+)?[A-Z][a-z]{2,}))\b", message)]
            skip = {'Order', 'Orders', 'Show', 'Which', 'What', 'Chase', 'Draft', 'Remind', 'Make', 'Add', 'Note', 'Log', 'Record', 'Compare', 'Is', 'Are', 'Can', 'Does', 'Did', 'Has', 'Was', 'Who', 'The', 'My', 'Please', 'Okay', 'Just', 'Since', 'For', 'Among', 'Between', 'Update', 'Refresh', 'Trace', 'Check', 'Find', 'Identify', 'Spot', 'Rank', 'Give', 'Tell', 'Keep', 'Leave', 'Clarify', 'Moving', 'Someone', 'When', 'Nothing', 'Four', 'Two', 'Three', 'Seven', 'New', 'Quick', 'Expedite', 'Prioritize', 'Prioritise', 'Generate', 'Email', 'Assess', 'Faster', 'Partial', 'Hidden', 'Same', 'Export', 'Embroidery', 'Cutting', 'Sewing', 'Inspection', 'Mittens', 'Vests', 'Jacket', 'Uniform', 'Top', 'Top'}
            for n in names:
                first = n.split()[0]
                if first in skip or 'ORD' in n.upper(): continue
                if re.search(r'\b(Apparel|Textiles?|Garments?|Fashion|Clothing|Trading|Mills?|Knits?|Co\.?|Ltd|Inc|Corp|Group|Brands?|Wear|Basics|Threads?)\b', n):
                    return n
        return None

    def grounding_check(self, message: str, slots: Slots, intent: Intent, result: Classification, state: DialogState, now: datetime,
                        calls: list[ToolCall], evidence: list[Evidence], explicit_ids: list[str]) -> ChatResponse | None:
        if intent in (Intent.UNANSWERABLE, Intent.UNKNOWN):
            return None
        lowered = message.casefold()
        products = sorted({e.record['product'] for e in self.tools.rows('orders.csv')})
        notes = []
        # 1. orders that do not exist
        missing = self.foreign_order_numbers(message, explicit_ids)
        if missing:
            state.slots = Slots(action=slots.action)
            state.comparison_orders = []
            state.active_order = None
            state.last_order_ids = []
            state.chase_context = {}
            for oid in missing:
                calls.append(ToolCall(name='refresh_order', arguments={'order_id': oid}, result={'status': 'not_found', 'order_id': oid}, executed=True))
            ids = ', '.join(missing)
            text = (f"There is no order {ids} in the current records. Order IDs run ORD-001 to ORD-{len(self.tools.rows('orders.csv')):03d}; check the number or give the customer and product instead."
                    if len(missing) == 1 else f"None of {ids} is in the current records (order IDs run ORD-001 to ORD-{len(self.tools.rows('orders.csv')):03d}). Check the numbers; nothing was compared, drafted, noted or scheduled.")
            if intent.value.startswith('execution.'):
                text += ' Nothing was drafted, saved or scheduled.' if len(missing) == 1 else ''
            return self.response(state, result, now, text, calls, evidence)
        # 2. a stage this factory does not have
        stage = self.foreign_stage(message)
        if stage and intent in (Intent.OPERATIONS_NORMALITY, Intent.OPERATIONS_DEVIATION, Intent.OPERATIONS_OUTPUT, Intent.ORDER_EXPEDITE, Intent.ORDER_PRIORITIZE, Intent.ORDER_RANK, Intent.ORDER_REFRESH,
                             Intent.ORDER_LOOKUP, Intent.ORDER_RISK, Intent.EXECUTION_REMINDER, Intent.EXECUTION_CHASE, Intent.ORDER_COMPARE, Intent.OPERATIONS_DISCOVERY) \
                and not (intent in (Intent.EXECUTION_CHASE, Intent.EXECUTION_NOTE) and (explicit_ids or state.active_order) and slots.action in ('revise', 'send', 'read')):
            if intent == Intent.EXECUTION_CHASE and (explicit_ids or state.active_order) and slots.action == 'draft':
                pass   # a chase about a real order whose text mentions a foreign stage: the chase_chat path notes the department instead
            else:
                calls.append(ToolCall(name='explain_no_data', arguments={'reason': 'unknown_stage', 'stage': stage}, result={'declined': True, 'stages_on_file': STAGE_ORDER}, executed=False))
                text = f"There is no {stage} stage in this factory's records: the stages are knitting → assembly → washing → packing, and only those four have output, queues or departments on file."
                when = re.search(r'\b(20\d{2}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)? (?:january|february|march|april|may|june|july|august|september|october|november|december)(?: 20\d{2})?|(?:january|february|march|april|may|june|july|august|september|october|november|december) \d{1,2})\b', lowered)
                if when:
                    try:
                        d = parse_day(when.group(0), now) or resolve_date(when.group(0), now)
                        latest = max(e.record['date'] for e in self.tools.rows('production_log.csv'))
                        if d and d.isoformat() > latest:
                            text += f" Also, the production log ends {latest} (business date {now.date().isoformat()}), so no output exists for {d.isoformat()} yet."
                    except Exception:
                        pass
                if intent == Intent.EXECUTION_REMINDER:
                    text += ' Say which of the four stages to watch and I will set the reminder.'
                elif intent == Intent.EXECUTION_CHASE:
                    text += ' Say which department (knitting, assembly, washing or packing) or workshop (W1–W8) should receive the chase, and which order.'
                else:
                    text += ' Ask about one of those stages instead.'
                state.pending_clarification = None
                return self.response(state, result, now, text, calls, evidence)
        # 3. a product or order type the records do not hold
        if intent not in (Intent.ORDER_COMMITMENT, Intent.ORDER_FORECAST, Intent.EXECUTION_NOTE) and not (intent == Intent.EXECUTION_CHASE and slots.action in ('revise', 'send', 'read')):
            tag = self.foreign_tag(message, slots)
            product = None if tag else self.foreign_product(message, slots)
            if tag or product:
                word = (tag or product)
                word = word[:-1] if word.endswith('s') and not word.endswith('ss') and word not in ('dress',) else word
                calls.append(ToolCall(name='search_orders', arguments={'product': word}, result={'candidates': [], 'products_on_file': products}, executed=True))
                state.slots = Slots(action=slots.action)
                state.comparison_orders = []
                state.active_order = None
                if tag:
                    text = (f"The records do not tag orders as '{tag}': each order carries customer, product, pieces, due date, stage and last activity only, so '{tag} orders' cannot be selected. "
                            f"Products on file: {', '.join(products)}; customers: {', '.join(known_customers(self.tools))}. Name a product or a customer and I will run the same question.")
                else:
                    text = f"No {word} orders in the records. Products on file: {', '.join(products)}. Name one of those (or a customer) and I will run the same question."
                return self.response(state, result, now, text, calls, evidence)
        # 4. a customer that is not on file
        if intent in (Intent.ORDER_LOOKUP, Intent.ORDER_COMPARE, Intent.EXECUTION_CHASE, Intent.ORDER_EXPEDITE, Intent.ORDER_PRIORITIZE, Intent.ORDER_RANK, Intent.EXECUTION_NOTE, Intent.ORDER_RISK, Intent.ORDER_REFRESH) \
                and not (intent == Intent.EXECUTION_CHASE and slots.action in ('revise', 'send', 'read')):
            customer = self.foreign_customer(message, slots)
            if customer:
                calls.append(ToolCall(name='search_orders', arguments={'customer': customer}, result={'candidates': [], 'customers_on_file': known_customers(self.tools)}, executed=True))
                state.slots = Slots(action=slots.action)
                state.comparison_orders = []
                state.active_order = None
                text = f"No customer named {customer} in the records. Customers on file: {', '.join(known_customers(self.tools))}. Nothing was changed; name one of them and I will run the same question."
                return self.response(state, result, now, text, calls, evidence)
        # 4b. "the third order from yesterday's planning meeting": meetings and conversations are not in the records
        if intent in (Intent.EXECUTION_NOTE, Intent.EXECUTION_CHASE, Intent.ORDER_LOOKUP, Intent.ORDER_RISK, Intent.ORDER_REFRESH, Intent.ORDER_EXPEDITE, Intent.EXECUTION_REMINDER) \
                and not explicit_ids and not state.active_order and not slots.customer and not slots.product \
                and re.search(r"(from|at|in|of) (yesterday'?s?|today'?s?|this morning'?s?|monday'?s?|tuesday'?s?|wednesday'?s?|thursday'?s?|friday'?s?|the|our|last) (planning |production |morning )?meeting|we (discussed|talked about|spoke about|went through) (on|at|in|yesterday|last)", lowered):
            calls.append(ToolCall(name='explain_no_data', arguments={'reason': 'meeting'}, result={'declined': True}, executed=False))
            text = 'Meeting notes and conversations are not in the records, and no order is in focus in this chat, so "the order from the meeting" cannot be resolved. Give the order ID (or customer and product) and I will do it.'
            return self.response(state, result, now, text, calls, evidence)
        # 5. a workshop that is not on file (chases and reminders only; a note may mention anything)
        if intent in (Intent.EXECUTION_CHASE, Intent.EXECUTION_REMINDER, Intent.WORKSHOPS) and slots.action != 'read':
            shop = self.foreign_workshop(message, slots)
            if shop:
                on_file = sorted({e.record['workshop_id'] for e in self.tools.rows('workshops.csv')}, key=lambda w: int(w[1:]))
                calls.append(ToolCall(name='list_workshops', arguments={'workshop': shop}, result={'status': 'not_found', 'workshops_on_file': on_file}, executed=True))
                text = f"{shop} is not a workshop on file: the workshops are {on_file[0]}–{on_file[-1]}. Nothing was drafted or sent; say which workshop or department should receive it."
                return self.response(state, result, now, text, calls, evidence)
        return None

    def not_found(self, order_id: str, state: DialogState, result: Classification, now: datetime,
                  calls: list[ToolCall], evidence: list[Evidence]) -> ChatResponse:
        """Sprint 2 (cause E): an unknown order ID is an answer, not an HTTP error."""
        state.active_order = None
        state.last_order_ids = []
        calls.append(ToolCall(name='refresh_order', arguments={'order_id': order_id}, result={'status': 'not_found', 'order_id': order_id}, executed=True))
        return self.response(state, result, now, f'There is no order {order_id} in the current records. Order IDs run ORD-001 to ORD-{len(self.tools.rows("orders.csv")):03d}; check the number or give the customer and product instead.', calls, evidence)

    def infer_lookup_slots(self, message: str, candidates: list[str], now: datetime) -> dict[str, Any]:
        """Sprint 2 (cause B): read product / quantity / due-date words from the manager's reply to a candidate list.
        Only values that actually distinguish the listed candidates are used; nothing is guessed."""
        lowered = message.casefold()
        records = [e.record for e in self.tools.rows('orders.csv') if e.record['order_id'] in set(candidates)]
        inferred: dict[str, Any] = {}
        products = {r['product'] for r in records}
        hit = [p for p in products if p.casefold() in lowered or p.casefold().rstrip('s') in lowered or (p.casefold().endswith('f') and p.casefold()[:-1] + 'ves' in lowered)]
        if len(hit) == 1:
            inferred['product'] = hit[0]
        quantity = re.search(r'\b(\d{2,5})\s*(?:-\s*)?(?:piece|pieces|pcs|pc)\b', lowered)
        if quantity and any(int(r['pieces']) == int(quantity[1]) for r in records):
            inferred['quantity'] = int(quantity[1])
        day = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b', lowered) \
            or re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b', lowered)
        if day:
            parts = day.groups()
            number, month = (parts[0], parts[1]) if parts[0].isdigit() else (parts[1], parts[0])
            months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
            m = months.index(month[:3]) + 1
            for r in records:
                due = r['due_date']
                if due.endswith(f'-{m:02d}-{int(number):02d}'):
                    inferred['due_date'] = due
                    break
        iso = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', lowered)
        if iso and any(r['due_date'] == iso[1] for r in records):
            inferred['due_date'] = iso[1]
        customers = {r['customer'] for r in records}
        hit = [c for c in customers if c.casefold() in lowered]
        if len(hit) == 1 and len(customers) > 1:
            inferred['customer'] = hit[0]
        return inferred

    def select(self, order_id: str, state: DialogState, calls: list[ToolCall], evidence: list[Evidence]) -> Evidence:
        """场景 1.1/1.2：唯一识别后刷新字段，保存 active_order 和客户。"""
        order = self.tools.refresh_order(order_id)
        calls.append(ToolCall(name='refresh_order', arguments={'order_id': order_id}, result=order.record))
        evidence.append(order)
        state.active_order = order_id
        state.active_customer = order.record['customer']
        state.comparison_orders = []
        state.last_order_ids = [order_id]
        return order

    @staticmethod
    def order_facts(order: Evidence) -> str:
        """场景 1.1–1.4：只展示正式订单记录，不生成虚构活动描述。"""
        row = order.record
        status = {'IN_PROGRESS': 'in progress', 'COMPLETE': 'complete'}.get(row['status'], str(row['status']).lower().replace('_', ' '))
        return (f"{row['order_id']} — {row['customer']}, {row['pieces']} {row['product']}: "
                f"{status}, stage {str(row['current_stage']).lower()}, due {row['due_date']}; "
                f"last recorded activity {row['last_activity_date']}." +
                (f" Completed {row['completed_date']}; recorded days late: {row['days_late']}." if row['status'] == 'COMPLETE' else ''))

    def propose(self, kind: Literal['send', 'note', 'reminder'], order_id: str, payload: dict[str, Any], preview: str,
                state: DialogState, now: datetime) -> None:
        """场景 3.1–3.3：每次预览生成新确认键，把动作、订单和最终内容绑定。"""
        snapshot = {} if order_id.startswith('STAGE:') else self.tools.refresh_order(order_id).record
        state.pending_action = PendingAction(kind=kind, order_id=order_id, payload=payload, preview=preview,
                                             created_at=now, source_snapshot=snapshot)

    def execution(self, message: str, result: Classification, state: DialogState, now: datetime,
                  calls: list[ToolCall], evidence: list[Evidence], order: Evidence, previous_slots: Slots) -> ChatResponse:
        """场景 3.1–3.3：草稿修订、内部备注预览和可更新条件提醒。"""
        slots, order_id = state.slots, order.record['order_id']
        if result.intent == Intent.EXECUTION_CHASE:
            if slots.action == 'send':
                if not state.draft or state.draft['order_id'] != order_id:
                    return self.ask('Please draft the message and specify its recipient first.', state, result, now, calls, evidence)
                preview = f"Ready to send to {state.draft['recipient']} about {order_id}:\n{state.draft['text']}\nPlease confirm 'send now'."
                self.propose('send', order_id, state.draft.copy(), preview, state, now)
                return self.response(state, result, now, preview, calls, evidence)
            recipient = slots.recipient or (state.draft or {}).get('recipient')
            if not recipient:
                return self.ask('Who should receive the draft?', state, result, now, calls, evidence)
            text = (state.draft or {}).get('text') if slots.action == 'revise' and (state.draft or {}).get('order_id') == order_id else None
            text = slots.text or text or f'Please provide an updated status, recovery plan and expected completion date for {order_id}. Please treat this as a priority. Thank you.'
            if slots.deadline:
                deadline = resolve_datetime(slots.deadline, now)
                if deadline is None:
                    return self.ask('What exact response date and time should the draft use?', state, result, now, calls, evidence)
                text = re.sub(r'\nPlease respond by .*', '', text) + f'\nPlease respond by {deadline.isoformat()}.'
            state.draft = {'order_id': order_id, 'recipient': recipient, 'text': text, 'tone': slots.tone or 'firm but polite'}
            calls.append(ToolCall(name='draft_chase', arguments={'order_id': order_id}, result=state.draft))
            answer = f"Unsent draft to {recipient} ({state.draft['tone']}):\n{text}\nDraft only; nothing has been sent."
        elif result.intent == Intent.EXECUTION_NOTE:
            lowered_q = message.casefold()
            pending_note = state.pending_action if state.pending_action and state.pending_action.kind == 'note' else None
            if pending_note and (slots.action == 'update' or re.match(r'^\s*(add|also|and|append|change|correct|make it|update)\b', lowered_q)) and slots.text:
                merged = slots.text if re.match(r'^\s*(change|correct|make it|update)\b', lowered_q) else (pending_note.payload.get('text', '') + '; ' + slots.text).strip('; ')
                target = pending_note.order_id
                preview = f'Internal note for {target}, business date {now.date()}:\n{merged}\nPlease confirm to save. It will not be sent externally.'
                self.propose('note', target, {'text': merged, 'visibility': 'internal'}, preview, state, now)
                calls.append(ToolCall(name='save_internal_note', arguments={'order_id': target, 'action': 'amend_pending'}, result={'text': merged}, executed=False))
                return self.response(state, result, now, preview, calls, evidence)
            asks_existing = (not slots.text and '?' in message) or bool(re.search(r'\b(already have|has anyone noted|is there (a|any) note|does .* have a note|which order (is|was) the note|show me the (original|existing)|was it logged|did (i|we) (log|note)|skip it if)\b', lowered_q))
            if asks_existing:
                saved = self.saved_notes(order_id)
                calls.append(ToolCall(name='save_internal_note', arguments={'order_id': order_id, 'action': 'read'}, result={'notes': saved}, executed=False))
                state.pending_action = None
                if saved:
                    listed = '\n'.join(f"- {n.get('created_at', '')[:16]}: {n.get('text', '')}" for n in saved[:8])
                    return self.response(state, result, now, f"{order_id} has {len(saved)} saved note{'s' if len(saved) != 1 else ''}:\n{listed}\nNothing was added. Say what to add if it is missing.", calls, evidence)
                return self.response(state, result, now, f'No saved note on {order_id} in this workspace. Nothing was added; tell me the wording if you want one recorded.', calls, evidence)
            if not slots.text:
                return self.ask('What exact internal note should I attach?', state, result, now, calls, evidence)
            target_is_explicit = order_id in message.upper()
            target_is_confirmed = slots.action == 'confirm_target' and bool(re.match(r'^(yes\b|是|对)', message.strip(), re.IGNORECASE))
            if not target_is_explicit and not target_is_confirmed:
                return self.ask(f'Internal note target is {order_id}. Is that the correct order?', state, result, now, calls, evidence)
            lowered = message.casefold()
            prefix = ''
            if re.search(r'\b(cancel|cancelled|canceled|take it off|remove (it )?from|delete|drop it)\b', lowered + ' ' + slots.text.casefold()):
                prefix = ('I cannot cancel or remove orders, or change the schedule: the chat reads the records and saves internal notes only. '
                          'I can record the intent as a note:\n')
            workshop = detect_workshop(slots.text + ' ' + message, self.tools)
            anyway = bool(re.search(r'\b(anyway|regardless|record it|go ahead|yes)\b', lowered))
            if workshop and not anyway:
                category = order.record['category']
                problems = []
                if workshop['status'] != 'ACTIVE':
                    problems.append(f"{workshop['name']} is {workshop['status']}" + (f" ({workshop['notes']})" if workshop.get('notes') else ''))
                if category not in workshop['makes'].split('+'):
                    problems.append(f"{workshop['name']} ({workshop['workshop_id']}) makes {workshop['makes']} only; {order_id} is {category} ({order.record['product'].lower()})")
                if problems:
                    alternatives = [f"{e.record['workshop_id']} {e.record['name']} ({e.record['capacity_pieces_per_day']}/day)" for e in self.tools.rows('workshops.csv')
                                    if e.record['status'] == 'ACTIVE' and category in e.record['makes'].split('+') and e.record['workshop_id'] != workshop['workshop_id']]
                    calls.append(ToolCall(name='list_workshops', arguments={'workshop_id': workshop['workshop_id'], 'category': category}, result={'problems': problems, 'alternatives': alternatives}))
                    return self.ask('; '.join(problems) + '. Record the note anyway, or choose another workshop? Active workshops that make ' + category.lower() + ': ' + (', '.join(alternatives) or 'none') + '.', state, result, now, calls, evidence)
            preview = f'{prefix}Internal note for {order_id}, business date {now.date()}:\n{slots.text}\nPlease confirm to save. It will not be sent externally.'
            self.propose('note', order_id, {'text': slots.text, 'visibility': 'internal'}, preview, state, now)
            answer = preview
        elif result.intent == Intent.EXECUTION_REMINDER and slots.condition == 'no_status_change_briefing':
            if not getattr(self, 'order_records', None):
                return self.ask('The shared order record service is unavailable.', state, result, now, calls, evidence)
            try:
                day = date.fromisoformat(slots.target_date or '')
                report_day = date.fromisoformat(slots.deadline or '')
            except ValueError:
                return self.ask('Which business day should I check, and which morning briefing should include the result?', state, result, now, calls, evidence)
            if day < now.date() or report_day <= day:
                return self.ask('Choose today or a future observation day, and a later briefing date.', state, result, now, calls, evidence)
            answer = propose_watch(self, state, order_id, day, report_day, now, message)
        elif result.intent == Intent.EXECUTION_REMINDER:
            lowered = message.casefold()
            progress = re.search(r"(hasn.t|has not|still not|no new|not) (finished|moved|progress|advanced|left)|still (hasn.t|has not) finished|still at", lowered)
            reply = re.search(r"(hasn.t|has not|no) (replied|reply|confirmed|answered|responded|come back)|without (a )?(reply|confirmation)", lowered)
            if progress and reply and ' and ' in lowered:
                return self.ask('I can watch one condition per reminder: no new activity recorded for the order, or no reply to the chase-up. '
                                'Which should this reminder check? I can create a second reminder for the other condition.', state, result, now, calls, evidence)
            if not slots.condition:
                if reply and not progress:
                    slots.condition = 'no_reply'
                elif progress and not reply:
                    slots.condition = 'no_activity'
                else:
                    return self.ask('Should I remind you only if no reply or no new activity is recorded?', state, result, now, calls, evidence)
            existing = self.store.get_reminder(state.session_id, order_id, slots.condition)
            prior_text = previous_slots.deadline or ''
            previous = resolve_datetime(prior_text, now) or resolve_datetime(prior_text.replace('morning', 'noon'), now)
            if existing and not previous:
                previous = datetime.fromisoformat(existing['deadline'])
            deadline = resolve_datetime(slots.deadline or '', now, previous)
            if deadline is None:
                return self.ask('What exact time on that date (for example Friday at 9 a.m.) should I check?', state, result, now, calls, evidence)
            if deadline <= now:
                return self.ask('The reminder time must be in the future. What date and time?', state, result, now, calls, evidence)
            slots.deadline = deadline.isoformat()
            since = datetime.fromisoformat(existing['since']) if existing else now
            meaning = {'no_activity': f"no new production activity has been recorded for {order_id} since {since.date().isoformat()} (its last_activity_date and stage are unchanged)",
                       'no_reply': f"no reply to the chase-up for {order_id} has been recorded since {since.date().isoformat()}"}.get(slots.condition, f"{slots.condition} is still unmet in recorded data")
            preview = (f"{'Update existing' if existing else 'Create'} reminder for {order_id} at {deadline.isoformat()}: notify only if {meaning}; "
                       f"otherwise nothing is sent. Please confirm.")
            self.propose('reminder', order_id, {'condition': slots.condition, 'deadline': deadline.isoformat(),
                         'since': existing['since'] if existing else now.isoformat()}, preview, state, now)
            answer = preview
        else:
            return self.ask('Please clarify the requested action.', state, result, now, calls, evidence)
        return self.response(state, result, now, answer, calls, evidence)

    async def confirm(self, request: ChatRequest, state: DialogState, now: datetime) -> ChatResponse:
        """场景 3.1–3.3：确认门禁、过期检测、状态刷新与真实执行结果。"""
        result = Classification(intent=state.last_intent or Intent.UNKNOWN, slots=state.slots, confidence=1)
        action = state.pending_action
        calls: list[ToolCall] = []
        evidence: list[Evidence] = []
        if request.confirmation_id:
            if getattr(self, 'order_records', None) and self.order_records.confirmed(request.confirmation_id, state.session_id):
                if action and action.id == request.confirmation_id:
                    state.pending_action = None
                return self.response(state, result, now, 'Already recorded. No duplicate record was created.', calls, evidence)
            prior = self.store.action_result(request.confirmation_id, state.session_id)
            if prior and prior['status'] in ('saved', 'sent'):
                return self.response(state, result, now, f"Already recorded: {prior['kind']} {prior['status']}; no duplicate action.", calls, evidence)
        if not action or (request.confirmation_id and request.confirmation_id != action.id):
            return self.ask('No matching pending action. Request a new preview before confirming.', state, result, now, calls, evidence)
        if now < action.created_at or now - action.created_at > timedelta(minutes=15):
            state.pending_action = None
            return self.ask('The preview expired. Please request a fresh preview.', state, result, now, calls, evidence)
        command = request.message.casefold()
        if ('send' in command or '发送' in command) and action.kind != 'send' or ('save' in command or '保存' in command) and action.kind != 'note':
            return self.ask('That confirmation does not match the previewed action.', state, result, now, calls, evidence)
        if request.selected_order_id and request.selected_order_id != action.order_id:
            return self.ask('The selected order changed. Request a new preview for the intended order.', state, result, now, calls, evidence)
        for oid, snapshot in action.source_snapshots.items():
            if self.tools.refresh_order(oid).record != snapshot:
                state.pending_action = None
                return self.ask('An order changed. Please review a fresh draft before sending.', state, result, now, calls, evidence)
        refreshed = self.tools.refresh_order(action.order_id) if action.order_id and not action.order_id.startswith('STAGE:') else None
        if refreshed:
            evidence.append(refreshed)
            calls.append(ToolCall(name='refresh_order', arguments={'order_id': action.order_id}, result=refreshed.record))
        if action.source_snapshot and refreshed.record != action.source_snapshot:
            state.pending_action = None
            return self.ask('The order record changed after the preview. Review the fresh record and request a new preview.', state, result, now, calls, evidence)
        if action.kind == 'reminder' and datetime.fromisoformat(action.payload['deadline']) <= now:
            state.pending_action = None
            return self.ask('The reminder deadline passed before confirmation. Please choose a future time.', state, result, now, calls, evidence)
        if action.kind == 'send' and (action.payload.get('send_at') or getattr(self,'email_scheduler',None)):
            scheduler = getattr(self,'email_scheduler',None)
            try:
                if not scheduler:
                    outcome = {'status':'not_sent','reason':'Email is not configured.'}
                elif action.payload.get('send_at'):
                    outcome = await asyncio.to_thread(scheduler.enqueue,action,now)
                else:
                    outcome = await scheduler.send_now(action,now)
            except ValueError:
                outcome = {'status':'not_sent','reason':'Provide a valid recipient email address before scheduling.'}
        elif getattr(self, 'order_records', None) and (action.kind == 'note' or action.payload.get('channel') == 'morning_briefing'):
            outcome = self.order_records.save(action, state.session_id, now)
        else:
            outcome = await self.store.send(action, state.session_id, now, self.sender) if action.kind == 'send' else self.store.commit_local(action, state.session_id, now)
        calls.append(ToolCall(name={'send': 'send_chase', 'note': 'save_internal_note', 'reminder': 'upsert_reminder'}[action.kind],
                              arguments={'action_id': action.id, 'order_id': action.order_id, **action.payload},
                              result=outcome, requires_confirmation=True, executed=outcome['status'] != 'not_sent'))
        if outcome['status'] in ('sent', 'saved', 'scheduled', 'accepted'):
            if action.kind == 'send':
                answer = 'Message sent; recipient, final text, send time and receipt recorded.'
            elif action.kind == 'note':
                answer = f'Internal note saved to {action.order_id} with timestamp. It was not sent externally.'
            elif action.payload.get('channel') == 'morning_briefing':
                answer = f"Follow-up saved for {action.order_id}. Check day: {action.payload['observation_day']}. Morning briefing: {action.payload['report_day']}."
            elif action.payload.get('condition') == 'stage_below_range':
                answer = (f"Watch {'updated' if 'Update' in action.preview else 'created'} on {action.payload['stage'].lower()}: at {action.payload['deadline']} you will be notified "
                          f"only if its output is still below the same-weekday range. Nothing is sent outside the system.")
            else:
                answer = (f"Reminder {'updated' if 'Update' in action.preview else 'created'} for {action.order_id}: at {action.payload['deadline']} you will be notified "
                          f"only if {action.payload['condition'].replace('_', ' ')} is still the case. Nothing is sent outside the system.")
            if outcome['status'] == 'scheduled':
                answer = 'Email scheduled for '+action.payload['send_at']+'. It has not been sent yet. View its status in Activity Log.'
                state.chase_context.pop('send_at',None)
            if outcome['status'] == 'accepted':
                answer = 'Microsoft accepted the email to '+action.payload['recipient']+'. The reviewed message and result are recorded in Activity Log. Inbox delivery is not confirmed.'
            for draft in state.chase_drafts:
                if draft.get('text') == action.payload.get('text') and draft.get('recipient') == action.payload.get('recipient'):
                    draft['sent'] = True
            state.pending_action = None
        else:
            answer = outcome.get('reason') or {'rejected':'Microsoft rejected this email. Check the details in Activity Log.',
                'unknown':'Submission is uncertain. Check Sent Items and Activity Log before sending again.',
                'sending':'This email is already being submitted. Check Activity Log.',
                'submitting':'This email has already been submitted. Check Activity Log.'}.get(outcome['status'],'Check the email result in Activity Log.')
            if getattr(self, 'email_scheduler', None) and outcome['status'] in ('rejected','unknown','sending','submitting'):
                # A fresh send must start with a fresh review; never silently resubmit.
                state.pending_action = None
        return self.response(state, result, now, answer, calls, evidence)
