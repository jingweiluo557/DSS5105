"""Questions about a set of orders that one tool call used to answer only in general terms.

The held-out evaluation (evaluation/heldout, 9 Nov) showed the same gap several ways: the question names a filter or a
superlative ("due between two dates", "finished in March", "next due after today", "oldest by order date", "which customer
has the most pieces", "which of them is due soonest", "total pieces across those") and the reply was a generic summary or
a ranking on another key. Each shape here is computed from orders.csv with the rule stated in the answer, the rows it used
attached as evidence, and one recorded tool call (`query_orders`) so the trace shows the filter and the key.

Nothing here guesses: a shape answers only when its own words are present; otherwise `answer` returns None and the
normal routing runs. All dates are compared with the business date the engine passes in.
"""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime

from ..schemas import Classification, DialogState, Intent, ToolCall

STAGE_ORDER = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING']
MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS['sept'] = 9
READ_INTENTS = {Intent.ORDER_SUMMARY, Intent.RISK_OVERVIEW, Intent.ORDER_RANK, Intent.ORDER_COMPARE, Intent.ORDER_LOOKUP, Intent.ORDER_PRIORITIZE, Intent.UNKNOWN}
ISO = r'\d{4}-\d{2}-\d{2}'
DAY = r'(?:' + ISO + r'|\d{1,2}(?:st|nd|rd|th)?\s+[a-z]{3,9}|[a-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?|the\s+\d{1,2}(?:st|nd|rd|th))'


def _day(text: str, today: date) -> date | None:
    """'2026-04-11', '11 April', 'Apr 11', 'the 19th' (this month). Nothing else: an unclear date is not guessed."""
    t = text.strip().casefold()
    if re.fullmatch(ISO, t):
        try: return date.fromisoformat(t)
        except ValueError: return None
    m = re.fullmatch(r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})', t) or re.fullmatch(r'([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?', t)
    if m:
        a, b = m.groups()
        d, mon = (a, b) if a.isdigit() else (b, a)
        if mon in MONTHS:
            try: return date(today.year, MONTHS[mon], int(d))
            except ValueError: return None
    m = re.fullmatch(r'the\s+(\d{1,2})(?:st|nd|rd|th)', t)
    if m:
        try: return date(today.year, today.month, int(m.group(1)))
        except ValueError: return None
    return None


def _label(r: dict) -> str:
    return f"{r['order_id']} ({r['customer']}, {int(r['pieces']):,} {r['product']})"


def _idle(r: dict, today: date) -> int:
    return (today - date.fromisoformat(r['last_activity_date'])).days


def _overdue(r: dict, today: date) -> int:
    return (today - date.fromisoformat(r['due_date'])).days


def _customer(engine, message: str) -> str | None:
    named = engine.customers_named(message)
    return named[0] if len(named) == 1 else None


def _stage(message: str) -> str | None:
    from ..workflow_engine import stages_in
    found = stages_in(message)
    return found[0] if len(found) == 1 else None


def _scope(engine, message: str):
    """Customer and stage named in the message narrow every shape; the words go into the answer."""
    customer, stage = _customer(engine, message), _stage(message)
    words = (f' for {customer}' if customer else '') + (f' at {stage.lower()}' if stage else '')
    def keep(r: dict) -> bool:
        return (not customer or r['customer'] == customer) and (not stage or r['current_stage'] == stage)
    return keep, words, {'customer': customer, 'stage': stage}


def _finish(engine, state: DialogState, result: Classification, now: datetime, text: str, rows: list, arguments: dict, data: dict,
            listed: list[str] | None = None, focus: str | None = None):
    call = ToolCall(name='query_orders', arguments={k: v for k, v in arguments.items() if v not in (None, '', [])}, result=data)
    state.pending_clarification = None
    state.comparison_orders = []
    if listed is not None:
        state.last_order_ids = listed
    state.active_order = focus
    return engine.response(state, result, now, text, [call], rows)


def answer(engine, message: str, result: Classification, state: DialogState, now: datetime):
    """A ChatResponse when the message is one of the shapes above, else None."""
    if result.intent not in READ_INTENTS or re.search(r'\bORD-\d{3}\b', message, re.I):
        return None
    m = message.casefold().replace('’', "'")
    today = now.date()
    every = [e for e in engine.tools.rows('orders.csv')]
    active = [e for e in every if e.record['status'] == 'IN_PROGRESS']
    for shape in (_follow_up, _due_between, _completed_in_month, _next_due, _by_order_date, _customer_superlative):
        out = shape(engine, m, message, result, state, now, today, every, active)
        if out is not None:
            return out
    return None


def _due_between(engine, m, message, result, state, now, today, every, active):
    hit = re.search(r'\bdue\b[^.?!]*?\b(?:between|from)\s+(' + DAY + r')\s*(?:and|to|until|through|thru|-|–)\s*(' + DAY + r')', m)
    if not hit:
        return None
    start, end = _day(hit.group(1), today), _day(hit.group(2), today)
    if not start or not end:
        return None
    if end < start: start, end = end, start
    keep, words, scope = _scope(engine, message)
    rows = sorted([e for e in every if start.isoformat() <= e.record['due_date'] <= end.isoformat() and keep(e.record)], key=lambda e: (e.record['due_date'], e.record['order_id']))
    done = [e for e in rows if e.record['status'] == 'COMPLETE']
    n = len(rows)
    text = f"{n} order{'s are' if n != 1 else ' is'} due between {start.isoformat()} and {end.isoformat()} (both days included){words}"
    text += (': ' + '; '.join(f"{_label(e.record)} due {e.record['due_date']}, {'complete' if e.record['status'] == 'COMPLETE' else 'at ' + e.record['current_stage'].lower()}" for e in rows) + '.') if rows else '.'
    if rows:
        text += f" {len(done)} of them {'is' if len(done) == 1 else 'are'} already complete." if done else ' None of them is complete yet.'
    return _finish(engine, state, result, now, text, rows, {'filter': 'due_date between', 'from': start.isoformat(), 'to': end.isoformat(), **scope},
                   {'count': n, 'order_ids': [e.record['order_id'] for e in rows], 'complete': len(done)}, [e.record['order_id'] for e in rows])


def _completed_in_month(engine, m, message, result, state, now, today, every, active):
    if not re.search(r'\b(how many|which|what|list|number of|count)\b', m):
        return None
    hit = re.search(r'\b(?:finish(?:ed)?|complet(?:e|ed|ion)|ship(?:ped)?|deliver(?:ed)?|clos(?:e|ed)|done)\b[^.?!]*?\b(?:in|during|for)\s+(?:the month of\s+)?(last month|this month|' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')\b(?:\s+(\d{4}))?', m)
    if not hit:
        return None
    word, year = hit.group(1), hit.group(2)
    if word == 'this month':
        y, mo = today.year, today.month
    elif word == 'last month':
        y, mo = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    else:
        mo = MONTHS[word]
        y = int(year) if year else (today.year if mo <= today.month else today.year - 1)   # the most recent such month
    first, last = date(y, mo, 1), date(y, mo, monthrange(y, mo)[1])
    keep, words, scope = _scope(engine, message)
    rows = sorted([e for e in every if e.record['status'] == 'COMPLETE' and e.record.get('completed_date') and first.isoformat() <= e.record['completed_date'] <= last.isoformat()
                   and (not scope['customer'] or e.record['customer'] == scope['customer'])], key=lambda e: (e.record['completed_date'], e.record['order_id']))
    words = f" for {scope['customer']}" if scope['customer'] else ''
    late = [e for e in rows if str(e.record.get('days_late') or '0').lstrip('-').isdigit() and int(e.record['days_late']) > 0]
    n = len(rows)
    month_name = first.strftime('%B %Y')
    text = f"{n} order{'s were' if n != 1 else ' was'} completed in {month_name}{words} (completed date {first.isoformat()} to {last.isoformat()})."
    if rows:
        text += f" {n - len(late)} on or before the due date, {len(late)} late."
        text += (' They are: ' + ', '.join(e.record['order_id'] for e in rows) + '.') if n <= 12 else f" First {rows[0].record['order_id']} on {rows[0].record['completed_date']}, last {rows[-1].record['order_id']} on {rows[-1].record['completed_date']}."
    if last >= today >= first:
        text += f' The month is not over: this counts up to the business date {today.isoformat()}.'
    return _finish(engine, state, result, now, text, rows, {'filter': 'completed_date in month', 'month': first.strftime('%Y-%m'), 'customer': scope['customer']},
                   {'count': n, 'on_time': n - len(late), 'late': len(late), 'order_ids': [e.record['order_id'] for e in rows]}, [e.record['order_id'] for e in rows][:34])


def _next_due(engine, m, message, result, state, now, today, every, active):
    future_only = re.search(r'\bafter today\b|\bfrom tomorrow\b|not (yet )?(over)?due yet|\bnot counting (the )?(overdue|late)|\b(ignoring|excluding|apart from|besides|other than) (the )?(overdue|late)|\bupcoming\b', m)
    if not (future_only and re.search(r'\bdue\b|\bdeadline|\bnext\b', m)) or re.search(r'\b(how many|count)\b', m):
        return None
    keep, words, scope = _scope(engine, message)
    rows = sorted([e for e in active if e.record['due_date'] > today.isoformat() and keep(e.record)], key=lambda e: (e.record['due_date'], e.record['order_id']))
    overdue = sum(1 for e in active if e.record['due_date'] < today.isoformat() and keep(e.record))
    due_today = sum(1 for e in active if e.record['due_date'] == today.isoformat() and keep(e.record))
    if not rows:
        return _finish(engine, state, result, now, f'No active order{words} is due after {today.isoformat()}.', [], {'filter': 'due_date after business date', **scope}, {'count': 0}, [])
    top = rows[0].record
    tied = [e for e in rows if e.record['due_date'] == top['due_date']]
    days = (date.fromisoformat(top['due_date']) - today).days
    text = (f"Next due after today ({today.isoformat()}){words}: " + ' and '.join(_label(e.record) for e in tied) + f", due {top['due_date']} ({days} day{'s' if days != 1 else ''} away), "
            + ('stage ' + top['current_stage'].lower() if len(tied) == 1 else 'stages ' + ', '.join(e.record['current_stage'].lower() for e in tied)) + '.')
    rest = rows[len(tied):len(tied) + 4]
    if rest:
        text += ' After that: ' + '; '.join(f"{e.record['order_id']} due {e.record['due_date']}" for e in rest) + '.'
    text += f" Not counted: {overdue} already overdue and {due_today} due today."
    return _finish(engine, state, result, now, text, rows[:5], {'filter': 'active, due_date after business date', 'sort': 'due_date ascending', **scope},
                   {'next': [e.record['order_id'] for e in tied], 'due_date': top['due_date'], 'overdue_not_counted': overdue, 'due_today_not_counted': due_today},
                   [e.record['order_id'] for e in rows[:5]], top['order_id'] if len(tied) == 1 else None)


def _by_order_date(engine, m, message, result, state, now, today, every, active):
    old = re.search(r'\b(oldest|earliest|longest[- ](open|running|outstanding)|open(ed)? (the )?longest|been open (the )?longest)\b', m)
    new = re.search(r'\b(newest|latest|most recent(ly)?|youngest)\b', m)
    by_order_date = re.search(r'\border(ed)? date\b|\bdate (it was |they were )?(ordered|placed)\b|\bplaced\b|\bbooked\b|\breceived\b|\bcame in\b|\bon the books\b', m)
    plain_oldest = re.search(r'\b(oldest|newest|longest[- ]open)\s+(open|active|unfinished|in[- ]progress|live|current)?\s*orders?\b', m) or re.search(r'\bopen(ed)? (the )?longest\b', m)
    if not (old or new) or not (by_order_date or plain_oldest) or re.search(r'\bdue\b|deadline|activity|update|idle|stuck|moved|touched', m):
        return None
    keep, words, scope = _scope(engine, message)
    rows = sorted([e for e in active if keep(e.record)], key=lambda e: (e.record['order_date'], e.record['order_id']), reverse=bool(new and not old))
    if not rows:
        return _finish(engine, state, result, now, f'No active order{words}.', [], {'sort': 'order_date', **scope}, {'count': 0}, [])
    top = rows[0].record
    tied = [e for e in rows if e.record['order_date'] == top['order_date']]
    age = (today - date.fromisoformat(top['order_date'])).days
    which = 'Newest' if (new and not old) else 'Oldest'
    text = (f"{which} open order by order date{words}: " + ' and '.join(_label(e.record) for e in tied) + f", ordered {top['order_date']} ({age} days ago); "
            + (f"due {top['due_date']}, stage {top['current_stage'].lower()}." if len(tied) == 1 else 'see each below.'))
    if len(tied) == 1 and top['due_date'] < today.isoformat():
        text += f" It is {_overdue(top, today)} days overdue."
    rest = rows[len(tied):len(tied) + 3]
    if rest:
        text += ' Next: ' + '; '.join(f"{e.record['order_id']} ordered {e.record['order_date']}" for e in rest) + '.'
    text += ' Ranked on the order_date column of active orders only; this is not the due-date ranking.'
    return _finish(engine, state, result, now, text, rows[:4], {'filter': 'active', 'sort': 'order_date ' + ('descending' if which == 'Newest' else 'ascending'), **scope},
                   {'top': [e.record['order_id'] for e in tied], 'order_date': top['order_date']}, [e.record['order_id'] for e in rows[:4]], top['order_id'] if len(tied) == 1 else None)


def _customer_superlative(engine, m, message, result, state, now, today, every, active):
    asks_customer = re.search(r"\b(which|what) (customer|client|buyer|account)s?\b|^\W*who\b|\bwho('s| is| has| have)\b|\bwhose\b", m)
    hi = re.search(r'\b(most|highest|biggest|largest|greatest|top)\b', m)
    lo = re.search(r'\b(fewest|least|lowest|smallest)\b', m)
    if not asks_customer or not (hi or lo) or engine.customers_named(message):
        return None
    if re.search(r'\b(pieces|pcs|quantity|volume|units|garments)\b', m):
        metric, unit = 'pieces', 'active pieces'
    elif re.search(r'\borders?\b', m) and not re.search(r'\b(over ?due|late|delay|behind|risk|attention|idle|stale|stuck)', m):
        metric, unit = 'orders', 'active orders'
    else:
        return None      # "most late orders", "needs attention": the customer comparison already answers those
    stage = _stage(message)
    rows = [e for e in active if not stage or e.record['current_stage'] == stage]
    totals: dict[str, dict] = {}
    for e in rows:
        t = totals.setdefault(e.record['customer'], {'orders': 0, 'pieces': 0})
        t['orders'] += 1; t['pieces'] += int(e.record['pieces'])
    if not totals:
        return None
    ranked = sorted(totals, key=lambda c: (totals[c][metric] if lo else -totals[c][metric], c))
    best = totals[ranked[0]][metric]
    tied = [c for c in ranked if totals[c][metric] == best]
    where = f' at {stage.lower()}' if stage else ''
    word = ('fewest' if metric == 'orders' else 'least') if lo else 'most'
    def fig(c): return f"{totals[c]['pieces']:,} pieces across {totals[c]['orders']} active order{'s' if totals[c]['orders'] != 1 else ''}" if metric == 'pieces' else f"{totals[c]['orders']} active order{'s' if totals[c]['orders'] != 1 else ''} ({totals[c]['pieces']:,} pieces)"
    if len(tied) == 1:
        text = f"{tied[0]} has the {word} {unit}{where}: {fig(tied[0])}."
    else:
        text = f"A tie for the {word} {unit}{where}: " + ' and '.join(tied) + f", each with {best:,} {'pieces' if metric == 'pieces' else 'active orders'}."
    rest = [c for c in ranked if c not in tied]
    if rest:
        text += ' Then: ' + '; '.join(f"{c} {totals[c][metric]:,}" for c in rest) + '.'
    text += f" Counted over the {len(rows)} orders in progress{where} on {today.isoformat()}; completed orders are left out."
    return _finish(engine, state, result, now, text, rows, {'filter': 'active', 'group_by': 'customer', 'metric': metric, 'pick': 'min' if lo else 'max', 'stage': stage},
                   {'answer': tied, 'value': best, 'by_customer': {c: totals[c] for c in ranked}}, None)


def _follow_up(engine, m, message, result, state, now, today, every, active):
    """"total pcs across those?", "which of them is due soonest?": the orders the previous answer listed."""
    ids = state.last_order_ids
    if len(ids) < 2 or not re.search(r'\b(those|them|these|they|that lot|the ones)\b', m):
        return None
    by_id = {e.record['order_id']: e for e in every}
    rows = [by_id[i] for i in ids if i in by_id]
    if len(rows) < 2:
        return None
    shown = ', '.join(e.record['order_id'] for e in rows) if len(rows) <= 8 else f'the {len(rows)} orders just listed'
    if re.search(r'\b(total|sum|combined|altogether|in all|add up|how many|how much)\b', m) and re.search(r'\b(pcs|pieces|quantity|units|garments|volume)\b', m):
        total = sum(int(e.record['pieces']) for e in rows)
        parts = ' + '.join(f"{e.record['order_id']} {int(e.record['pieces']):,}" for e in rows) if len(rows) <= 8 else f'{len(rows)} orders'
        text = f"{total:,} pieces across those {len(rows)} orders: {parts}."
        return _finish(engine, state, result, now, text, rows, {'filter': 'orders from the previous answer', 'order_ids': ids, 'aggregate': 'sum pieces'}, {'total_pieces': total, 'count': len(rows)}, ids)
    if not re.search(r'\b(which|what|who)\b', m):
        return None
    open_rows = [e for e in rows if e.record['status'] == 'IN_PROGRESS']
    picks = [
        (r'most over ?due|most late|latest\b.*\b(late|overdue)|furthest behind|most behind', 'most overdue', open_rows, lambda e: (e.record['due_date'], e.record['order_id']), lambda r: f"due {r['due_date']}" + (f", {_overdue(r, today)} days overdue" if _overdue(r, today) > 0 else ', not overdue')),
        (r'due (the )?(soonest|first|next|earliest)|soonest|earliest (due|deadline)|first (due|to ship)|next (due|to ship)|due (date )?(is )?(closest|nearest)', 'due soonest', open_rows, lambda e: (e.record['due_date'], e.record['order_id']), lambda r: f"due {r['due_date']}" + (' (already overdue)' if _overdue(r, today) > 0 else '')),
        (r'due (the )?(last|latest)|latest (due|deadline)|most time', 'due last', open_rows, lambda e: (-date.fromisoformat(e.record['due_date']).toordinal(), e.record['order_id']), lambda r: f"due {r['due_date']}"),
        (r'biggest|largest|most (pcs|pieces)|highest quantity', 'biggest', rows, lambda e: (-int(e.record['pieces']), e.record['order_id']), lambda r: f"{int(r['pieces']):,} pieces"),
        (r'smallest|fewest (pcs|pieces)|least (pcs|pieces)|lowest quantity', 'smallest', rows, lambda e: (int(e.record['pieces']), e.record['order_id']), lambda r: f"{int(r['pieces']):,} pieces"),
        (r'idle|stuck|quiet|stalled|not moved|hasn.?t moved|longest (since|without)|least recent', 'idle longest', open_rows, lambda e: (e.record['last_activity_date'], e.record['order_id']), lambda r: f"last activity {r['last_activity_date']} ({_idle(r, today)} days ago)"),
        (r'further along|furthest along|closest to (done|finish|shipping|complete)|nearest (to )?(done|finish)', 'furthest along', open_rows, lambda e: (-STAGE_ORDER.index(e.record['current_stage']) if e.record['current_stage'] in STAGE_ORDER else 0, e.record['due_date'], e.record['order_id']), lambda r: f"at {r['current_stage'].lower()}"),
        (r'oldest|placed first|ordered first', 'oldest by order date', rows, lambda e: (e.record['order_date'], e.record['order_id']), lambda r: f"ordered {r['order_date']}"),
    ]
    for pattern, name, pool, key, fact in picks:
        if re.search(pattern, m):
            if not pool:
                return _finish(engine, state, result, now, f'None of {shown} is still in progress, so there is nothing to rank.', rows, {'order_ids': ids, 'pick': name}, {'count': 0}, ids)
            ranked = sorted(pool, key=key)
            top = ranked[0].record
            same = [e for e in ranked if key(e)[:-1] == key(ranked[0])[:-1]]
            if len(same) > 1:
                text = f"A tie among {shown} for {name}: " + ' and '.join(f"{_label(e.record)}, {fact(e.record)}" for e in same) + '.'
                focus = None
            else:
                text = f"Of {shown}, {name}: {_label(top)}, {fact(top)}; stage {top['current_stage'].lower()}."
                if len(ranked) > 1:
                    text += ' Next: ' + '; '.join(f"{e.record['order_id']} {fact(e.record)}" for e in ranked[1:3]) + '.'
                focus = top['order_id']
            return _finish(engine, state, result, now, text, rows, {'filter': 'orders from the previous answer', 'order_ids': ids, 'pick': name},
                           {'answer': [e.record['order_id'] for e in same], 'ranked': [e.record['order_id'] for e in ranked[:10]]}, ids, focus)
    return None


def remember_set(engine, result: Classification, state: DialogState, message: str) -> None:
    """After a summary narrowed to a customer, stage or product, 'them' / 'those' are that group's active orders."""
    s = result.slots
    customer = s.customer or _customer(engine, message)
    stage = s.stage or _stage(message)
    if not (customer or stage or s.product):
        return
    rows = [e.record for e in engine.tools.rows('orders.csv') if e.record['status'] == 'IN_PROGRESS'
            and (not customer or e.record['customer'].casefold() == customer.casefold())
            and (not stage or e.record['current_stage'] == str(stage).upper())
            and (not s.product or e.record['product'].casefold() == s.product.casefold())]
    if 2 <= len(rows) <= 34:
        state.last_order_ids = [r['order_id'] for r in rows]
        state.active_order = None


def stage_verdict(rows: list[dict], message: str) -> str:
    """One line under a two-order stage comparison: which is further along, on the fixed stage order."""
    a, b = rows
    def pos(r): return len(STAGE_ORDER) if r['status'] == 'COMPLETE' else (STAGE_ORDER.index(r['current_stage']) if r['current_stage'] in STAGE_ORDER else -1)
    flow = 'knitting → assembly → washing → packing'
    if pos(a) == pos(b):
        return f"Neither is further along: both are {'complete' if a['status'] == 'COMPLETE' else 'at ' + a['current_stage'].lower()} (stage order: {flow}). The records hold no progress inside a stage."
    ahead, behind = (a, b) if pos(a) > pos(b) else (b, a)
    where = lambda r: 'complete' if r['status'] == 'COMPLETE' else r['current_stage']
    gap = pos(ahead) - pos(behind)
    return (f"{ahead['order_id']} is further along: {where(ahead)} comes after {where(behind)} in the stage order ({flow}), {gap} stage{'s' if gap != 1 else ''} ahead of {behind['order_id']}. "
            f"This is position in the flow, not time left: the records hold no progress inside a stage.")


def pieces_verdict(rows: list[dict]) -> str:
    a, b = rows
    pa, pb = int(a['pieces']), int(b['pieces'])
    if pa == pb:
        return f"Same size: both are {pa:,} pieces."
    big, small = (a, b) if pa > pb else (b, a)
    return f"{big['order_id']} is bigger: {int(big['pieces'])} pieces vs {int(small['pieces'])} for {small['order_id']}."


def overdue_verdict(rows: list[dict], today: date) -> str | None:
    """'Which is more overdue': days past due for active orders; says so when one or both are not overdue."""
    a, b = rows
    da, db = _overdue(a, today), _overdue(b, today)
    def state_of(r, d):
        if r['status'] == 'COMPLETE': return 'complete'
        return f'{d} days overdue' if d > 0 else ('due today' if d == 0 else f'not overdue (due in {-d} days)')
    if a['status'] == 'COMPLETE' and b['status'] == 'COMPLETE':
        return 'Both orders are complete, so neither is overdue now.'
    if da <= 0 and db <= 0:
        return f"Neither is overdue: {a['order_id']} is {state_of(a, da)}, {b['order_id']} is {state_of(b, db)}."
    if da == db:
        return f"Equally overdue: both are {da} days past their due date."
    worse, other, dw, do = (a, b, da, db) if (da > db and a['status'] != 'COMPLETE') or b['status'] == 'COMPLETE' else (b, a, db, da)
    return f"{worse['order_id']} is more overdue: {dw} days past its {worse['due_date']} due date, against {other['order_id']} which is {state_of(other, do)}."
