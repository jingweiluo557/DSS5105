"""场景 1.1–3.3：模型识别、确定性路由、状态与确认闸门。"""
import asyncio
import json
import re
from contextlib import nullcontext
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Protocol

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
    return hits[0] if len(hits) == 1 else None


def detect_workshop(message: str, tools: DataTools) -> dict | None:
    lowered = message.casefold()
    for e in tools.rows('workshops.csv'):
        r = e.record
        if r['name'].casefold() in lowered or r['workshop_id'].casefold() in re.findall(r'\bw\d\b', lowered):
            return r
    return None


def stages_in(message: str) -> list[str]:
    lowered = message.casefold()
    return list(dict.fromkeys(code for word, code in STAGE_WORDS.items() if re.search(r'\b' + word + r'\b', lowered)))


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
        if confirmed and role != 'manager':
            # Sprint 2: a planner key can read, draft and preview; only the manager key confirms a write.
            response = self.response(state, Classification(intent=state.last_intent or Intent.UNKNOWN, confidence=1), now,
                                     'A manager key is required to confirm this action. The preview stays open for a manager to confirm.', [], [])
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
            if emit:
                await emit(response.answer)
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
        state.revision += 1
        state.history = (state.history + [{'role': 'user', 'content': request.message},
                                         {'role': 'assistant', 'content': response.answer}])[-16:]
        self.store.save(state)
        return response.model_copy(update={'state': state.model_copy(deep=True)})

    async def converse(self, request, agent, state, now, emit):
        from .conversation import summary_response
        plan = await agent.plan(request.message, state, now)
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
            if state.comparison_orders and not human_ids and not expanded[0].classification.slots.draft_number:
                response = self.ask('Which order do you mean: ' + ', '.join(state.comparison_orders) + '?', state, expanded[0].classification, now, [], [], state.comparison_orders)
                if emit: await emit(response.answer)
                return response
            from .services.chase_chat import chase_chat
            return await chase_chat(self, request.message, expanded[0].classification, state, now, agent, emit)
        for task in expanded:
            result = task.classification
            if result.intent == Intent.GENERAL:
                response = ChatResponse(answer='The model is unavailable. Please try your general question again later.', intent=Intent.GENERAL,
                    slots=Slots(), confidence=result.confidence, state=state, business_date=now.date().isoformat())
            elif result.intent in (Intent.ORDER_SUMMARY, Intent.RISK_OVERVIEW):
                response = summary_response(self, result, state, now, request.message)
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
        queried = list(dict.fromkeys(i for r in responses if r.intent in single_order_intents for i in r.order_ids))
        if len(queried) > 1:
            state.comparison_orders = queried
            state.active_order = None
            state.last_order_ids = queried
            state.slots.order_ids = []
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
        return message.strip().casefold().rstrip('.!。！') in {'send now', 'save it', 'confirm', 'confirm save', 'confirm create', 'confirm update', '确认', '确认发送', '确认保存', '确认创建', '确认更新'}

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
        if state.comparison_orders and not explicit_ids and not narrowed and intent not in entity_free:
            if mentions_order_reference(message) or slots.reference in ('active', 'ambiguous'):
                return self.ask('Which order do you mean: ' + ', '.join(state.comparison_orders) + '?', state, result, now, calls, evidence)
            state.comparison_orders = []   # the new question does not point at the compared orders at all
        if result.confidence < 0.65 or intent == Intent.UNKNOWN:
            return self.ask(result.clarification_question or 'Which order or operation would you like to check?', state, result, now, calls, evidence)
        comparative_ranking = intent == Intent.ORDER_COMPARE and (slots.action == 'rank' or slots.criterion is not None)
        if (slots.reference == 'ambiguous' and not comparative_ranking) or (state.comparison_orders and slots.reference == 'active' and not slots.order_ids and intent != Intent.ORDER_COMPARE):
            if state.comparison_orders:
                return self.ask('Which order do you mean: ' + ', '.join(state.comparison_orders) + '?', state, result, now, calls, evidence)
            if intent not in entity_free and not explicit_ids and not slots.customer and not slots.product:
                # "the order that was late yesterday": nothing is being compared, so the description itself names the candidates
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
                return self.ask(('Several matching orders. Which order ID, quantity or due date? ' + options) if matches else 'No matching order. Please check the order ID, quantity or due date.', state, result, now, calls, evidence, state.last_order_ids)
            order = self.select(matches[0].record['order_id'], state, calls, evidence)
            answer = self.order_facts(order)
        elif intent == Intent.ORDER_COMPARE:
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
            if not slots.comparison_fields:
                return self.ask('Which aspect matters: due date, stage, latest activity, status, pieces or overall delivery risk?', state, result, now, calls, evidence)
            rows = [self.tools.refresh_order(i) for i in ids]
            evidence.extend(rows)
            calls.append(ToolCall(name='compare_orders', arguments={'order_ids': ids, 'fields': slots.comparison_fields}, result={'records': [e.record for e in rows]}))
            if slots.action == 'rank' and not slots.criterion:
                return self.ask('Should I rank by overall delivery risk, due-date pressure or update recency?', state, result, now, calls, evidence)
            answer = '| Order | ' + ' | '.join(slots.comparison_fields) + ' |\n| --- | ' + ' | '.join('---' for _ in slots.comparison_fields) + ' |\n'
            answer += '\n'.join('| ' + e.record['order_id'] + ' | ' + ' | '.join(e.record[f] for f in slots.comparison_fields) + ' |' for e in rows)
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
            if slots.window_days is None:
                if re.search(r'this week|next (seven|7) days|7 days', lowered):
                    slots.window_days = 7
                else:   # the dialogue design asks "today only or the next seven days?" rather than guessing
                    return self.ask('Due today only, or include the next seven days? Overdue active orders will be included.', state, result, now, calls, evidence)
            data, rows = self.tools.prioritize(slots, now)
            evidence.extend(rows)
            calls.append(ToolCall(name='prioritize_orders', arguments={'window_days': slots.window_days, 'customer': slots.customer}, result=data))
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
            if not slots.delivery_point:
                return self.ask('Does the deadline mean ready at our factory or delivered to the customer?', state, result, now, calls, evidence)
            if not slots.quantity or not slots.product or not slots.due_date:
                return self.ask('What product, quantity and explicit due date should I estimate?', state, result, now, calls, evidence)
            if resolve_date(slots.due_date, now) <= now.date():
                return self.ask('That date is not in the future. What new delivery date should I assess?', state, result, now, calls, evidence)
            data, rows = self.tools.capacity(slots, now)
            evidence.extend(rows)
            calls.append(ToolCall(name='estimate_capacity', arguments=slots.model_dump(), result=data))
            answer = 'Conditional forecast, not a promise:\n' + json.dumps(data, ensure_ascii=False, indent=2)
        elif intent in (Intent.OPERATIONS_NORMALITY, Intent.OPERATIONS_DEVIATION, Intent.OPERATIONS_OUTPUT):
            return self.production(message, intent, result, slots, state, now, calls, evidence, previous_clarification)
        elif intent == Intent.OPERATIONS_DISCOVERY:
            data, rows = self.tools.find_anomalies(slots, now)
            evidence.extend(rows)
            calls.append(ToolCall(name='find_anomalies', arguments={'customer': slots.customer, 'stage': slots.stage, 'limit': data['shown']}, result=data))
            state.last_order_ids = [f['entity'] for f in data['findings'] if f['entity'].startswith('ORD-')][:10]
            state.active_order = None
            if not data['findings']:
                answer = f"Nothing unusual in the recorded data as of {data['business_date']}: no sustained stage drop, no stalled customer, no overdue or near-due miss, no idle order."
            else:
                answer = (f"{data['total']} finding{'s' if data['total'] != 1 else ''} as of {data['business_date']} ({', '.join(f'{v} {k.replace(chr(95), ' ')}' for k, v in data['by_kind'].items())}); top {data['shown']} by tier and score:\n" +
                          '\n'.join(f"{i}. [{f['tier']}] {f['title']}. {f['action']} (rule: {f['rule']})" for i, f in enumerate(data['findings'], 1)) +
                          '\n' + data['limits'])
        elif intent == Intent.ORDER_RANK:
            data, rows = self.tools.rank_active_orders(slots, now)
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
            if not order_id:
                return self.ask('Which order should I forecast? Please give its ID.', state, result, now, calls, evidence)
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

    def describe_candidates(self, message: str, now: datetime):
        """'the order that was late yesterday', 'the overdue order', 'the stalled order' -> the real candidates and a label."""
        lowered = message.casefold()
        today = now.date()
        active = [e for e in self.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS']
        if re.search(r'\b(late|overdue|past due|missed)\b', lowered):
            rows = sorted([e for e in active if e.record['due_date'] < today.isoformat()], key=lambda e: e.record['due_date'])
            return (f'{len(rows)} active orders are overdue as of {today.isoformat()}', rows) if rows else None
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
        return (f"{row['order_id']} — {row['customer']}, {row['pieces']} {row['product']}; "
                f"status {row['status']}, stage {row['current_stage']}, due {row['due_date']}, "
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
            preview = f"{'Update existing' if existing else 'Create'} reminder for {order_id} at {deadline.isoformat()}: notify only if {slots.condition} is still unmet in recorded data. Please confirm."
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
