"""Chase-ups drafted before the manager asks: one per stalled order, ready to review and send.

The home screen lists them under "Drafted for you"; "Review & send" opens the chat on the same preview the typed
chase-up reaches ("Review the drafted chase-up for ORD-002"), and only the manager's "Confirm send" sends it. Nothing
here sends, schedules or stores anything.

Which orders: in progress and stalled by the system's 5-day rule (calendar days since last_activity_date >= 5, the rule
the alert policy and the KPI strip use), overdue first, then longest idle; at most MAX_DRAFTS; an order chased in the last
RECENT_DAYS business days is left out. The text is written from the order record alone (no model), so it states only
what the record says, and it asks the department for a status and a finish date; it never promises the customer anything.
"""
from datetime import date

STALLED_DAYS = 5
MAX_DRAFTS = 3
RECENT_DAYS = 3


def _pieces(o: dict) -> str:
    try:
        return f"{int(float(o['pieces'])):,}"
    except (TypeError, ValueError, KeyError):
        return str(o.get('pieces', ''))


def compose(o: dict, today: date) -> dict:
    """Subject, body and department for one order, from its record."""
    stage = str(o['current_stage']).lower()
    idle = (today - date.fromisoformat(o['last_activity_date'])).days
    to_due = (date.fromisoformat(o['due_date']) - today).days
    due = (f"It was due {o['due_date']}, {-to_due} day{'s' if to_due != -1 else ''} ago." if to_due < 0
           else f"It is due today, {o['due_date']}." if to_due == 0
           else f"It is due {o['due_date']}, in {to_due} day{'s' if to_due != 1 else ''}.")
    text = (f"Hi {stage} team,\n\n"
            f"{o['order_id']} ({o['customer']}, {str(o['product']).lower()}, {_pieces(o)} pieces) is at {stage} and has had no recorded activity "
            f"since {o['last_activity_date']} ({idle} days). {due}\n\n"
            f"Please reply with its current status, what is holding it, and the date {stage} will finish.\n\nThank you.")
    return {'order_id': o['order_id'], 'department': o['current_stage'], 'subject': f"ThreadPilot chase-up | {o['order_id']}",
            'text': text, 'idle_days': idle, 'days_to_due': to_due}


def stalled(orders: list[dict], today: date) -> list[dict]:
    rows = [o for o in orders if str(o.get('status', '')).upper() in ('IN_PROGRESS', 'IN PROGRESS')
            and o.get('last_activity_date') and (today - date.fromisoformat(o['last_activity_date'])).days >= STALLED_DAYS]
    return sorted(rows, key=lambda o: (o['due_date'] >= today.isoformat(), o['last_activity_date'], o['order_id']))


def prepare(orders: list[dict], today: date, recently_chased=frozenset(), limit: int = MAX_DRAFTS) -> dict:
    """{'drafts': [...], 'skipped_recent': [...], 'rule': ...} for the home screen."""
    rows = stalled(orders, today)
    skipped = [o['order_id'] for o in rows if o['order_id'] in recently_chased]
    drafts = []
    for o in rows:
        if o['order_id'] in recently_chased:
            continue
        d = compose(o, today)
        d['reason'] = (f"{d['idle_days']} days without activity at {str(o['current_stage']).lower()}"
                       + (f", {-d['days_to_due']} days overdue" if d['days_to_due'] < 0 else ''))
        d['customer'] = o['customer']
        drafts.append(d)
        if len(drafts) >= limit:
            break
    return {'drafts': drafts, 'more': max(0, len(rows) - len(skipped) - len(drafts)), 'skipped_recent': skipped,
            'rule': f'in progress, no recorded activity for {STALLED_DAYS}+ days; not chased in the last {RECENT_DAYS} days'}


def recently_chased(jobs: list[dict], today: date) -> set[str]:
    """Order IDs with a chase email sent, accepted, scheduled or sending in the last RECENT_DAYS business days."""
    out = set()
    for job in jobs or []:
        if job.get('status') not in ('sent', 'accepted', 'scheduled', 'sending', 'submitting'):
            continue
        when = str(job.get('scheduled_at') or job.get('updated_at') or '')[:10]
        try:
            if (today - date.fromisoformat(when)).days <= RECENT_DAYS:
                out.update(job.get('order_ids') or [])
        except ValueError:
            continue
    return out
