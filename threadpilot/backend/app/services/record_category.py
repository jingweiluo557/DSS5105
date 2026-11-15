"""Conservative routing of records; classification never schedules or sends anything."""
import re


def category(kind, payload):
    if kind != 'note':
        return 'follow_up'
    if payload.get('category') in ('note', 'follow_up'):
        return payload['category']
    text = payload.get('text', '').strip()
    # Completed actions and explicit negation are context, not new tasks.
    if re.search(r'\b(already|completed|resolved|no need|do not|don.t)\b|已完成|已跟进|无需|不需要|不用', text, re.I):
        return 'note'
    if re.search(r'\b(?:(?:please|need to|must)\s+(?:confirm|contact|check|call|chase|review|follow)|to do|todo|follow[- ]?up|remind me|awaiting|pending)\b|待办|待跟进|请.*(?:确认|联系|跟进|检查|催)|需要.*(?:确认|联系|跟进|检查|催)|提醒我', text, re.I):
        return 'follow_up'
    if re.search(r'^(?:tomorrow[, ]+)?(?:follow up|chase|check|contact|confirm|call|review)\b|^(?:明天|后天|下周).*(?:确认|联系|跟进|检查|催)', text, re.I):
        return 'follow_up'
    return 'note'
