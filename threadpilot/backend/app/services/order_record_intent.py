"""Recognize explicit notes and today's conditional watch for tomorrow's briefing."""
import re
from datetime import datetime, time, timedelta

from ..business_clock import LOCAL
from ..schemas import Classification, Intent, Slots

ORDER = re.compile(r'(?:ord(?:er)?)[\s#-]*(\d{1,3})(?!\d)', re.I)
NOTE = re.compile(r'(?:备注(?:一下|下)?|加(?:一条|个)备注)\s*[:：，,]?\s*(.+)', re.S)
BRIEFING = re.compile(r'晨报|morning (?:report|brief(?:ing)?)', re.I)
UNCHANGED = re.compile(r'(?:没|未|无|没有|不).{0,4}(?:更新|变化|变动)|no (?:status |stage )?(?:change|update)|unchanged|(?:hasn.t|doesn.t|not|no).{0,16}(?:updated?|changed?)', re.I)


def preview(engine, message, state, now, selected=None):
    previous = state.pending_clarification
    if previous and previous.question == 'Which single order should this record belong to?' and ORDER.fullmatch(message.strip()) and previous.slots.text:
        message = message.strip() + ' ' + ORDER.sub('', previous.slots.text)
    note = NOTE.search(message)
    watch = BRIEFING.search(message) and UNCHANGED.search(message) and re.search(r'状态|工序|阶段|status|stage', message, re.I)
    if watch and not (re.search(r'今天|今日|today', message, re.I) and re.search(r'明天|明早|明日|tomorrow', message, re.I)):
        return None  # Other dates use the planner's structured business-date slots.
    if not watch and (not note or BRIEFING.search(message) or re.search(r'查看|查询|有哪些|删除|取消|改备注|不要备注|别备注', message)):
        return None
    ids = list(dict.fromkeys('ORD-' + n.zfill(3) for n in ORDER.findall(message)))
    oid = ids[0] if len(ids) == 1 else None
    if not ids and re.search(r'这(?:个|笔)?单|这(?:个|笔)?订单|this order', message, re.I):
        oid = selected or state.active_order
    intent = Intent.EXECUTION_REMINDER if watch else Intent.EXECUTION_NOTE
    result = Classification(intent=intent, confidence=1)
    state.pending_action = None
    if not oid:
        state.slots = Slots(text=message)
        return engine.ask('Which single order should this record belong to?', state, result, now, [], [])
    try:
        evidence = engine.tools.refresh_order(oid)
    except (KeyError, ValueError):
        return engine.ask(f'Order {oid} was not found. Which order did you mean?', state, result, now, [], [])
    state.active_order = oid
    state.last_intent = intent
    state.slots = Slots(order_ids=[oid])
    state.pending_clarification = None
    if watch:
        day = now.astimezone(LOCAL).date()
        next_day = day + timedelta(days=1)
        summary = propose_watch(engine, state, oid, day, next_day, now, message)
        return engine.response(state, result, now, summary, [], [evidence])
    else:
        body = note.group(1).strip()
        if not body or len(body) > 2000:
            return engine.ask('Please supply a note of 1–2000 characters.', state, result, now, [], [evidence])
        payload = dict(text=body, visibility='internal')
        summary = f'{oid} · 内部备注：{body}\n确认保存？'
        kind = 'note'
    engine.propose(kind, oid, payload, summary, state, now)
    return engine.response(state, result, now, summary, [], [evidence])


def propose_watch(engine, state, oid, day, next_day, now, message):
    payload = dict(condition='no_status_change', channel='morning_briefing',
        observation_day=str(day), report_day=str(next_day),
        deadline=datetime.combine(day + timedelta(days=1), time.min, LOCAL).isoformat())
    summary = (f'{oid} · 检查 {day} 全天的订单状态或生产阶段。若无变化，将在 {next_day} 晨报提醒；'
               '若记录不完整，将标为无法核实。确认创建？' if re.search(r'[\u4e00-\u9fff]',message)
               else f'{oid}: Check status and stage changes throughout {day}. Report no change or incomplete history in the {next_day} morning briefing. Confirm?')
    engine.propose('reminder', oid, payload, summary, state, now)
    return summary
