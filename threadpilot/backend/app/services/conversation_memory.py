"""Conversation memory across several orders in one chat.

A manager asks about ORD-005, then ORD-120, then says "go back to the first one", "is the other one late?", "compare
both of them" or "chase the scarf one". The planner model sees only the current message plus a short history, so it
cannot reliably turn those words into an order. The server can: it keeps the orders discussed in this conversation
(first mention order and most recent) and rewrites an unambiguous reference into the explicit order ID before the
planner runs. Explicit IDs then go through the normal, already-tested path.

Rules (deterministic, nothing guessed):
  * Only references that point at orders already discussed (or at the list the system just showed) are rewritten.
  * A message that already names an order ID is never rewritten.
  * An ordinal right after a candidate list ("the first one") picks from that list; otherwise from the conversation.
  * A description ("the scarf one", "the TrendCart order we discussed") is rewritten only when exactly one discussed
    order matches it; otherwise the message is left alone and the normal ask-don't-guess rules apply.
Every rewrite is reported back (a recall_conversation tool call and a one-line note), so the manager sees what it took.
"""
from __future__ import annotations

import re

from ..schemas import DialogState

MAX_REMEMBERED = 12
ORDINALS = {'first': 0, '1st': 0, 'second': 1, '2nd': 1, 'third': 2, '3rd': 2, 'fourth': 3, '4th': 3, 'fifth': 4, '5th': 4}
ORDINAL_RE = re.compile(r'\b(?:the\s+)?(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|last)\s+(?:one|order)\b', re.I)
OTHER_RE = re.compile(r'\b(?:the\s+)?(other|previous|earlier)\s+(?:one|order)\b', re.I)
BOTH_RE = re.compile(r'\b(both of them|both orders|both of these|them both|the two orders|these two orders|those two orders|these two|those two|the two of them)\b', re.I)
COMPARE_THEM_RE = re.compile(r'\b(compare)\s+(them|the two)\b', re.I)
DESCRIBED_RE = re.compile(r"\b(?:the|that)\s+([a-z][a-z&' -]{1,40}?)\s+(?:one|order)(?:\s+(?:we|i)\s+(?:discussed|talked about|looked at|asked about|checked))?\b", re.I)
ID_RE = re.compile(r'\bORD-\d{3}\b', re.I)


def remember(state: DialogState, order_ids: list[str]) -> None:
    """Add orders to the conversation's memory: first-mention order for ordinals, recency for "the other one"."""
    for oid in order_ids:
        if not oid:
            continue
        if oid not in state.discussed_orders:
            state.discussed_orders.append(oid)
        if oid in state.recent_orders:
            state.recent_orders.remove(oid)
        state.recent_orders.append(oid)
    state.discussed_orders[:] = state.discussed_orders[-MAX_REMEMBERED:]
    state.recent_orders[:] = state.recent_orders[-MAX_REMEMBERED:]


def _records(tools, ids: list[str]) -> dict[str, dict]:
    wanted = set(ids)
    return {e.record['order_id']: e.record for e in tools.rows('orders.csv') if e.record['order_id'] in wanted}


def _matches(record: dict, words: str) -> bool:
    words = words.casefold().strip()
    product, customer = record['product'].casefold(), record['customer'].casefold()
    singular = words[:-1] if words.endswith('s') else words
    return (words in (product, product + 's', customer) or singular == product or product in words.split()
            or customer in words or (product.endswith('f') and words == product[:-1] + 'ves'))


def recall(message: str, state: DialogState, tools) -> tuple[str, list[dict]]:
    """Rewrite references to earlier orders into explicit IDs. Returns (message for the planner, notes)."""
    if ID_RE.search(message):
        return message, []
    pending = state.pending_clarification
    candidates = list(pending.candidates) if pending and pending.candidates else []
    notes: list[dict] = []

    def swap(text: str, span: tuple[int, int], replacement: str, phrase: str, ids: list[str], source: str) -> str:
        notes.append({'phrase': phrase.strip(), 'order_ids': ids, 'from': source})
        return text[:span[0]] + replacement + text[span[1]:]

    m = ORDINAL_RE.search(message)
    if m:
        pool, source = (candidates, 'the list just shown') if candidates else (state.discussed_orders, 'this conversation')
        word = m.group(1).casefold()
        if word == 'last' and not candidates:
            pool = state.discussed_orders
        index = len(pool) - 1 if word == 'last' else ORDINALS[word]
        if pool and index < len(pool) and (candidates or len(pool) >= 2):
            return swap(message, m.span(), pool[index], m.group(0), [pool[index]], source), notes
        return message, []
    if candidates:
        return message, []   # a reply to a candidate list is narrowed by the existing rules
    if len(state.discussed_orders) < 2:
        return message, []
    m = OTHER_RE.search(message)
    if m:
        current = state.active_order or state.recent_orders[-1]
        others = [o for o in state.recent_orders if o != current]
        if others:
            return swap(message, m.span(), others[-1], m.group(0), [others[-1]], 'this conversation'), notes
    m = BOTH_RE.search(message) or COMPARE_THEM_RE.search(message)
    if m:
        pair = state.comparison_orders[:2] if len(state.comparison_orders) >= 2 else state.recent_orders[-2:]
        if len(pair) == 2:
            if m.re is COMPARE_THEM_RE:
                return swap(message, m.span(2), f'{pair[0]} and {pair[1]}', m.group(0), pair, 'this conversation'), notes
            return swap(message, m.span(), f'{pair[0]} and {pair[1]}', m.group(0), pair, 'this conversation'), notes
    for m in DESCRIBED_RE.finditer(message):
        words = m.group(1)
        if words.casefold() in ('first', 'second', 'third', 'last', 'other', 'previous', 'earlier', 'same', 'new', 'next', 'late', 'overdue', 'urgent'):
            continue
        records = _records(tools, state.discussed_orders)
        hits = [oid for oid in state.discussed_orders if oid in records and _matches(records[oid], words)]
        if len(hits) == 1:
            return swap(message, m.span(), hits[0], m.group(0), hits, 'this conversation'), notes
    return message, []


def note_line(notes: list[dict]) -> str:
    """One line the manager reads above the answer, so a rewrite is never silent."""
    parts = [f'“{n["phrase"]}” = {" and ".join(n["order_ids"])}' for n in notes]
    where = notes[0]['from'] if notes else ''
    return f'(Reading {"; ".join(parts)}, from {where}.)'
