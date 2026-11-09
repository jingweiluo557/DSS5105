"""Chase-ups drafted before the manager asks (home screen "Drafted for you"): which orders, what the text says, and that
"Review & send" only previews; the send still needs the manager's confirmation of that exact email."""
import csv
import types
from datetime import date
from pathlib import Path

from app.services import ready_drafts
from tests.test_sprint2_fixes import ScriptedPlanner, chat
from tests.test_workflow import make_engine

TODAY = date(2026, 4, 1)
ORDERS = list(csv.DictReader((Path(__file__).resolve().parents[2] / 'data' / 'orders.csv').open(encoding='utf-8')))


def test_stalled_orders_are_drafted_overdue_first_from_the_record():
    out = ready_drafts.prepare(ORDERS, TODAY)
    assert [d['order_id'] for d in out['drafts']] == ['ORD-002', 'ORD-005']      # the two orders idle 5+ days; ORD-002 is overdue
    d = out['drafts'][0]
    assert d['department'] == 'WASHING' and d['idle_days'] == 9 and d['days_to_due'] == -3
    assert 'since 2026-03-23 (9 days)' in d['text'] and 'It was due 2026-03-29, 3 days ago.' in d['text']
    assert d['text'].startswith('Hi washing team,') and 'customer' not in d['text'].lower()   # written to the department, never the customer
    # an order chased in the last 3 days is not drafted again
    again = ready_drafts.prepare(ORDERS, TODAY, {'ORD-002'})
    assert [d['order_id'] for d in again['drafts']] == ['ORD-005'] and again['skipped_recent'] == ['ORD-002']
    assert ready_drafts.recently_chased([{'status': 'sent', 'scheduled_at': '2026-03-30T10:00:00+08:00', 'order_ids': ['ORD-002']},
                                         {'status': 'rejected', 'scheduled_at': '2026-04-01T09:00:00+08:00', 'order_ids': ['ORD-005']},
                                         {'status': 'sent', 'scheduled_at': '2026-03-20T10:00:00+08:00', 'order_ids': ['ORD-010']}], TODAY) == {'ORD-002'}


class Mailbox:
    outlook = types.SimpleNamespace(settings=None, missing=lambda: False)

    def __init__(self):
        self.sent = []

    async def send_now(self, action, now):
        self.sent.append(action.payload)
        return {'status': 'sent', 'receipt': 'test'}


def _mail_settings(monkeypatch):
    fake = types.ModuleType('app.services.email_settings')

    class EmailSettings:
        def __init__(self, settings): pass

        def read(self):
            return {'manager_email': 'gm@example.com', 'departments': {'WASHING': 'washing@example.com', 'KNITTING': 'knitting@example.com'}}
    fake.EmailSettings = EmailSettings
    monkeypatch.setitem(__import__('sys').modules, 'app.services.email_settings', fake)


def test_review_and_send_previews_the_drafted_email_and_sends_only_on_confirm(tmp_path: Path, monkeypatch):
    _mail_settings(monkeypatch)
    engine = make_engine(tmp_path)
    engine.email_scheduler = mailbox = Mailbox()
    planner = ScriptedPlanner()          # the planner is never asked: the button's words route the turn
    r = chat(engine, planner, 'Review the drafted chase-up for ORD-002')
    assert r.confirmation_required and r.confirmation_id
    assert r.answer.startswith('Drafted for you from the record: ORD-002 has had no recorded activity for 9 days.')
    assert 'To: washing@example.com' in r.answer and 'Subject: ThreadPilot chase-up | ORD-002' in r.answer
    assert mailbox.sent == [] and not any(c.name == 'send_chase' and c.executed for c in r.tool_calls)
    r = chat(engine, planner, 'send now', r.state, r.confirmation_id)
    assert [p['recipient'] for p in mailbox.sent] == ['washing@example.com']
    assert mailbox.sent[0]['text'].startswith('Hi washing team,') and mailbox.sent[0]['order_ids'] == ['ORD-002']


def test_review_and_send_refuses_orders_not_in_progress(tmp_path: Path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(), 'Review the drafted chase-up for ORD-001')
    assert r.answer == 'ORD-001 is no longer in progress, so there is nothing to chase. Nothing was sent.'
    assert not r.confirmation_required
