"""Regression tests for the fixes that the held-out evaluation of 9 Nov led to (evaluation/heldout, 22 of 70 not passed).

Each test names the held-out item it came from, and most add a sibling question worded differently, with the expected
value computed here from orders.csv by separate code, so a fix that only fits the original wording fails.
Scripted planners: these test the server (routing, tools, wording), not the language model.
"""
import csv
from datetime import date
from pathlib import Path

from app.services.order_refs import expand_shorthand, normalize_order_numbers, normalize_order_refs
from app.schemas import DialogState
from tests.test_sprint2_fixes import ScriptedPlanner, chat
from tests.test_workflow import DATA, NOW, make_engine

TODAY = NOW.date()
ROWS = list(csv.DictReader(open(Path(DATA) / 'orders.csv', newline='')))
ACTIVE = [r for r in ROWS if r['status'] == 'IN_PROGRESS']
KNOWN = {int(r['order_id'][4:]) for r in ROWS}
PRODUCTS = {r['product'] for r in ROWS}


def norm(text):
    return normalize_order_numbers(normalize_order_refs(expand_shorthand(text)), KNOWN, PRODUCTS)


def ask(tmp_path, intent, slots, message):
    return chat(make_engine(tmp_path), ScriptedPlanner((intent, slots)), message)


# ---------------------------------------------------------------- L05, L10, C03, C04, X03, X07, M02: loosely written order numbers
def test_hash_padded_and_or_numbers_become_order_ids_only_when_they_can_be_nothing_else():
    assert norm('#81 what stage') == 'ORD-081 what stage'
    assert norm('chase washing on #83. just send it') == 'chase washing on ORD-083. just send it'
    assert norm('remind me if 002 hasnt moved') == 'remind me if ORD-002 hasnt moved'
    assert norm("81 or 66 - which one's bigger") == "ORD-081 or ORD-066 - which one's bigger"
    assert norm('is 83 or 2 more overdue') == 'is ORD-083 or ORD-002 more overdue'
    # numbers that are not order numbers stay as they are
    assert norm('can we do it in 2 or 3 days, which is more realistic') == 'can we do it in 2 or 3 days, which is more realistic'
    assert norm('we need 500 or 600 pieces which first') == 'we need 500 or 600 pieces which first'
    assert norm('#1 priority today') == '#1 priority today'
    assert norm('call me at 9 or 10 am, which is better') == 'call me at 9 or 10 am, which is better'
    assert norm('output was 055 pieces') == 'output was 055 pieces'
    assert norm('#999 what stage') == '#999 what stage', 'no such order: left for the not-on-file answer'


def test_L03_L10_a_status_lookup_says_how_late_and_how_long_idle(tmp_path):
    r = ask(tmp_path, 'order.lookup', {'order_ids': ['ORD-107'], 'reference': 'explicit'}, 'order 107 status')
    late = (TODAY - date.fromisoformat(next(x for x in ROWS if x['order_id'] == 'ORD-107')['due_date'])).days
    assert f'{late} days overdue' in r.answer and 'packing' in r.answer
    r = ask(tmp_path / 'b', 'order.lookup', {'order_ids': ['ORD-002'], 'reference': 'explicit'}, '#2 when did anyone last touch it')
    assert 'ORD-002' in r.answer and '2026-03-23' in r.answer and 'No recorded activity for 9 days' in r.answer and not r.needs_clarification


# ---------------------------------------------------------------- A05, A08: counts with a date filter
def test_A05_orders_due_between_two_dates_are_counted_and_listed(tmp_path):
    r = ask(tmp_path, 'order.summary', {}, 'how many orders are due between 2026-04-11 and 2026-04-19')
    want = sorted(x['order_id'] for x in ROWS if '2026-04-11' <= x['due_date'] <= '2026-04-19')
    assert r.answer.startswith(f'{len(want)} orders are due between 2026-04-11 and 2026-04-19') and all(i in r.answer for i in want)
    assert r.tool_calls[0].name == 'query_orders' and sorted(r.tool_calls[0].result['order_ids']) == want
    # sibling: other dates, written another way, with a customer
    r = ask(tmp_path / 'b', 'order.summary', {}, 'which TrendCart orders are due from 10 April to 30 April?')
    want = sorted(x['order_id'] for x in ROWS if x['customer'] == 'TrendCart' and '2026-04-10' <= x['due_date'] <= '2026-04-30')
    assert sorted(r.tool_calls[0].result['order_ids']) == want and 'for TrendCart' in r.answer


def test_A08_orders_completed_in_a_month(tmp_path):
    r = ask(tmp_path, 'order.summary', {}, 'how many orders did we finish in march')
    want = [x for x in ROWS if x['status'] == 'COMPLETE' and x['completed_date'].startswith('2026-03')]
    assert r.answer.startswith(f'{len(want)} orders were completed in March 2026')
    r = ask(tmp_path / 'b', 'order.summary', {}, 'how many orders were completed in February?')
    want = [x for x in ROWS if x['status'] == 'COMPLETE' and x['completed_date'].startswith('2026-02')]
    assert r.answer.startswith(f'{len(want)} order') and 'February 2026' in r.answer
    # an ordinary summary is untouched
    r = ask(tmp_path / 'c', 'order.summary', {}, 'how many orders are overdue')
    assert r.answer.startswith('As of 2026-04-01')


# ---------------------------------------------------------------- R02, R06, R08: rankings on the key that was asked for
def test_R02_next_due_after_today_skips_overdue_and_due_today(tmp_path):
    r = ask(tmp_path, 'order.rank', {'criterion': 'due_date'}, "after today, what's the next order due?")
    nxt = min((x for x in ACTIVE if x['due_date'] > TODAY.isoformat()), key=lambda x: (x['due_date'], x['order_id']))
    assert r.answer.startswith('Next due after today') and nxt['order_id'] in r.answer.split('.')[0] and nxt['due_date'] in r.answer
    assert r.state.active_order == nxt['order_id'], 'a follow-up "who is it for" means this order'


def test_R06_oldest_open_order_is_ranked_on_order_date_not_due_date(tmp_path):
    r = ask(tmp_path, 'order.rank', {'criterion': 'due_date'}, 'oldest open order? (by order date)')
    old = min(ACTIVE, key=lambda x: (x['order_date'], x['order_id']))
    assert old['order_id'] in r.answer.split(';')[0] and old['order_date'] in r.answer and 'order_date' in r.tool_calls[0].arguments['sort']
    r = ask(tmp_path / 'b', 'order.rank', {}, 'which active order was placed most recently?')
    new = max(ACTIVE, key=lambda x: (x['order_date'], x['order_id']))
    assert new['order_date'] in r.answer and r.answer.startswith('Newest open order')


def test_R08_idle_ranking_respects_the_stage_named_in_the_question(tmp_path):
    r = ask(tmp_path, 'order.rank', {'criterion': 'idle_days', 'stage': 'KNITTING'}, "in knitting, what's been stuck longest")
    top = min((x for x in ACTIVE if x['current_stage'] == 'KNITTING'), key=lambda x: (x['last_activity_date'], x['due_date'], x['order_id']))
    first_line = r.answer.split('\n')[1]
    assert first_line.startswith('1. ' + top['order_id']) and 'at knitting' in r.answer.split('\n')[0]
    assert all('stage KNITTING' in line for line in r.answer.split('\n')[1:])
    # the planner left the stage out: the words still filter
    r = ask(tmp_path / 'b', 'order.rank', {'criterion': 'idle_days'}, 'which washing order has been idle the longest?')
    assert all('stage WASHING' in line for line in r.answer.split('\n')[1:])


# ---------------------------------------------------------------- R04, R05, C08: customers
def test_R04_R05_customer_with_the_most_pieces_and_the_fewest_orders(tmp_path):
    pieces, orders = {}, {}
    for x in ACTIVE:
        pieces[x['customer']] = pieces.get(x['customer'], 0) + int(x['pieces']); orders[x['customer']] = orders.get(x['customer'], 0) + 1
    r = ask(tmp_path, 'order.compare', {}, 'which customer has the most pieces in progress')
    top = max(pieces, key=pieces.get)
    assert r.answer.startswith(f'{top} has the most active pieces: {pieces[top]:,} pieces') and not r.needs_clarification
    r = ask(tmp_path / 'b', 'order.compare', {}, "who's got the fewest open orders with us")
    low = min(orders, key=lambda c: (orders[c], c))
    assert r.answer.startswith(f'{low} has the fewest active orders: {orders[low]} active orders')
    # "needs attention" keeps the existing overdue-first comparison
    r = ask(tmp_path / 'c', 'order.compare', {}, 'which customer needs attention most?')
    assert r.tool_calls[0].name == 'compare_orders'


def test_C08_two_customers_with_the_same_number_of_late_orders_is_a_tie(tmp_path):
    r = ask(tmp_path, 'order.compare', {}, 'maple & co vs northwind - which has more late orders?')
    assert 'Neither has more late orders: both have 2 overdue' in r.answer and 'ORD-083' in r.answer and 'ORD-107' in r.answer and not r.needs_clarification


# ---------------------------------------------------------------- C02, C03, C04, C07: a comparison ends with the verdict
def test_C02_C07_stage_comparison_says_which_is_further_along(tmp_path):
    r = ask(tmp_path, 'order.compare', {'order_ids': ['ORD-062', 'ORD-103'], 'reference': 'explicit', 'comparison_fields': ['current_stage']}, 'which is further along, ORD-062 or ORD-103')
    assert 'ORD-103 is further along: ASSEMBLY comes after KNITTING' in r.answer
    r = ask(tmp_path / 'b', 'order.compare', {'order_ids': ['ORD-114', 'ORD-109'], 'reference': 'explicit', 'comparison_fields': ['current_stage']}, '114 vs 109, which is closer to done')
    assert 'ORD-114 is further along: PACKING comes after WASHING' in r.answer


def test_C03_C04_size_and_overdue_comparisons_name_the_order(tmp_path):
    r = ask(tmp_path, 'order.compare', {'order_ids': ['ORD-081', 'ORD-066'], 'reference': 'explicit', 'comparison_fields': ['pieces']}, "81 or 66 - which one's bigger")
    assert 'ORD-081 is bigger: 1500 pieces vs 1000 for ORD-066.' in r.answer and not r.needs_clarification   # the two recorded figures only
    r = ask(tmp_path / 'b', 'order.compare', {'order_ids': ['ORD-083', 'ORD-002'], 'reference': 'explicit', 'comparison_fields': ['due_date']}, 'is 83 or 2 more overdue')
    assert 'ORD-083 is more overdue: 9 days' in r.answer and '3 days overdue' in r.answer
    # one of the two is not overdue: said plainly, no invented ranking
    r = ask(tmp_path / 'c', 'order.compare', {'order_ids': ['ORD-036', 'ORD-045'], 'reference': 'explicit', 'comparison_fields': ['due_date']}, 'ORD-036 or ORD-045, which is more overdue')
    assert 'Neither is overdue' in r.answer


# ---------------------------------------------------------------- X03, X07, N07: actions keep their rules
def test_X03_just_send_it_still_shows_the_draft_and_sends_nothing(tmp_path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'send', 'order_ids': ['ORD-083'], 'reference': 'explicit', 'department': 'WASHING'})), 'chase washing on #83. just send it, dont need to see it')
    # "#83" is read as ORD-083; with no mailbox in this fixture the reply asks who receives the draft, and nothing goes out
    assert 'ORD-083' in r.answer and 'Nothing is sent without a preview and your confirmation' in r.answer and engine.sender.sent == []


def test_X07_a_reminder_without_a_time_asks_for_the_time_and_names_the_order(tmp_path):
    r = ask(tmp_path, 'execution.reminder', {'action': 'create', 'order_ids': ['ORD-002'], 'reference': 'explicit', 'condition': 'no_activity'}, 'remind me if 002 hasnt moved')
    assert r.needs_clarification and 'ORD-002' in r.answer and 'date and time' in r.answer and not r.confirmation_required


def test_N07_a_workshop_name_that_is_not_on_file_gets_no_draft(tmp_path):
    engine = make_engine(tmp_path)
    r = chat(engine, ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-045'], 'reference': 'explicit', 'recipient': 'SilkRoute'})), 'chase the SilkRoute workshop on order 45')
    assert 'SilkRoute is not a workshop on file' in r.answer and 'Draft 1' not in r.answer and not r.confirmation_required and engine.sender.sent == []
    # a real workshop is still drafted for
    r = chat(make_engine(tmp_path / 'b'), ScriptedPlanner(('execution.chase', {'action': 'draft', 'order_ids': ['ORD-053'], 'reference': 'explicit', 'recipient': 'QuickStitch'})), 'chase the QuickStitch workshop on ORD-053')
    assert 'Draft 1' in r.answer and 'QuickStitch' in r.answer


# ---------------------------------------------------------------- M01, M02, M03, M06: follow-ups
def two_turns(tmp_path, first, second):
    engine, state = make_engine(tmp_path), DialogState()
    planner = ScriptedPlanner(first[:2], second[:2])
    chat(engine, planner, first[2], state)
    return chat(engine, planner, second[2], engine.store.load(state.session_id))


def test_M01_who_is_it_for_after_the_most_overdue_order(tmp_path):
    r = two_turns(tmp_path, ('order.prioritize', {'window_days': 0}, 'whats our most overdue order'), ('order.lookup', {'reference': 'active'}, "who's it for?"))
    worst = min(ACTIVE, key=lambda x: (x['due_date'], x['order_id']))
    assert worst['order_id'] in r.answer and worst['customer'] in r.answer and not r.needs_clarification


def test_M02_the_other_one_after_a_comparison_is_the_order_the_answer_did_not_pick(tmp_path):
    r = two_turns(tmp_path, ('order.compare', {'order_ids': ['ORD-053', 'ORD-036'], 'reference': 'explicit', 'comparison_fields': ['due_date']}, "053 or 036, which one's due first"),
                  ('order.lookup', {'reference': 'active'}, 'and what stage is the other one in'))
    assert 'ORD-036' in r.answer and 'knitting' in r.answer and 'ORD-053 —' not in r.answer


def test_M03_total_pieces_across_the_orders_just_listed(tmp_path):
    r = two_turns(tmp_path, ('order.prioritize', {'customer': 'Cotton Club', 'window_days': 0}, 'cotton club - which of their orders are overdue?'),
                  ('order.summary', {'customer': 'Cotton Club'}, 'total pcs across those?'))
    late = [x for x in ACTIVE if x['customer'] == 'Cotton Club' and x['due_date'] <= TODAY.isoformat()]
    assert r.answer.startswith(f"{sum(int(x['pieces']) for x in late):,} pieces across those {len(late)} orders")


def test_M06_which_of_them_is_due_soonest_after_a_customer_count(tmp_path):
    r = two_turns(tmp_path, ('order.summary', {'customer': 'TrendCart'}, 'how many open orders has trendcart got'),
                  ('order.lookup', {'customer': 'TrendCart', 'criterion': 'due_date'}, 'which of them is due soonest?'))
    first = min((x for x in ACTIVE if x['customer'] == 'TrendCart'), key=lambda x: (x['due_date'], x['order_id']))
    assert f"due soonest: {first['order_id']}" in r.answer and not r.needs_clarification
    # sibling: another customer, another superlative
    r = two_turns(tmp_path / 'b', ('order.summary', {'customer': 'Harbor Knits'}, 'how many open orders does Harbor Knits have'),
                  ('order.lookup', {'customer': 'Harbor Knits'}, 'which of those is the biggest?'))
    big = max((x for x in ACTIVE if x['customer'] == 'Harbor Knits'), key=lambda x: (int(x['pieces']), x['order_id']))
    assert int(big['pieces']) == max(int(x['pieces']) for x in ACTIVE if x['customer'] == 'Harbor Knits') and f"{int(big['pieces']):,} pieces" in r.answer


# ---------------------------------------------------------------- the alert email shown in Settings (14 Nov)
def test_alert_email_is_rationed_one_email_then_nothing_until_something_new():
    """What the Settings card and the demo show: the first check emails the urgent items once; the next check, with
    that email in the history, sends nothing and says why; the email names each item, its rule and how to mute it."""
    from app.services import alert_policy
    data = {'today': TODAY.isoformat(), 'orders': ROWS,
            'production_log': list(csv.DictReader(open(Path(DATA) / 'production_log.csv', newline=''))),
            'workshops': list(csv.DictReader(open(Path(DATA) / 'workshops.csv', newline='')))}
    first = alert_policy.gate(alert_policy.detect(data, NOW), [], NOW)
    urgent = [d for d in first if d.channel == 'email_now']
    assert 1 <= len(urgent) <= alert_policy.MAX_P1_PER_DAY
    mail = alert_policy.render_email(first, NOW, 'Manager')
    assert mail['subject'].startswith('[ThreadPilot P1]') and 'Rule:' in mail['body'] and 'Why you got this' in mail['body'] and 'Mute:' in mail['body']
    history = [{'key': d.alert.key, 'tier': d.alert.tier, 'score': d.alert.score, 'channel': d.channel, 'sent_at': NOW.isoformat()} for d in urgent]
    second = alert_policy.gate(alert_policy.detect(data, NOW), history, NOW)
    assert not [d for d in second if d.channel == 'email_now'], 'the same items are not emailed again'
    assert sum('already reported' in d.reason for d in second if d.channel == 'suppressed') == len(urgent)


def test_alert_history_ignores_undelivered_and_later_timeline_rows():
    """Found when asking why switching alert emails on sent nothing: every dry-run tick had been recorded as "reported",
    so the items were in cooldown for ever; and after moving the demo clock back, rows stamped later read as reported
    "-5 h ago". Neither reached the manager at that business time, so neither may hold an email back."""
    from datetime import timedelta
    from app.services import alert_policy
    data = {'today': TODAY.isoformat(), 'orders': ROWS,
            'production_log': list(csv.DictReader(open(Path(DATA) / 'production_log.csv', newline=''))),
            'workshops': list(csv.DictReader(open(Path(DATA) / 'workshops.csv', newline='')))}
    alerts = alert_policy.detect(data, NOW)
    urgent = [d for d in alert_policy.gate(alerts, [], NOW) if d.channel == 'email_now']
    row = lambda d, at, status: {'key': d.alert.key, 'tier': d.alert.tier, 'score': d.alert.score, 'channel': 'email_now', 'sent_at': at.isoformat(), 'status': status}
    emailed = lambda history, delivered_only: [d for d in alert_policy.gate(alerts, history, NOW, None, delivered_only) if d.channel == 'email_now']
    dry = [row(d, NOW - timedelta(hours=1), 'dry_run') for d in urgent]
    assert emailed(dry, False) == [], 'while emails are off, a dry run still counts, so the dry-run ledger does not repeat itself'
    assert len(emailed(dry, True)) == len(urgent), 'once emails are on, what was never delivered does not hold the first real email back'
    assert emailed([row(d, NOW - timedelta(hours=1), 'accepted') for d in urgent], True) == [], 'a delivered email does'
    later = [row(d, NOW + timedelta(days=3), 'accepted') for d in urgent]
    assert len(emailed(later, True)) == len(urgent), 'rows from a later timeline (the clock was moved back) are ignored'


def test_first_real_check_after_switching_on_sends_once_even_after_weeks_of_dry_runs(tmp_path):
    """The whole tick, as the timer and "Run the check now" call it, with a stand-in mailbox."""
    import asyncio
    from types import SimpleNamespace
    from app.services.alert_delivery import AlertDelivery, AlertLedger
    data = {'today': TODAY.isoformat(), 'orders': ROWS,
            'production_log': list(csv.DictReader(open(Path(DATA) / 'production_log.csv', newline=''))),
            'workshops': list(csv.DictReader(open(Path(DATA) / 'workshops.csv', newline='')))}
    sent = []
    prefs = {'manager_email': 'gm@example.com', 'manager_name': 'Wendy', 'alert_emails_enabled': False}
    delivery = AlertDelivery.__new__(AlertDelivery)
    delivery.settings = SimpleNamespace(alert_emails_enabled=False)
    delivery.ledger = AlertLedger(tmp_path / 'alerts.sqlite3')
    delivery.preferences = SimpleNamespace(read=lambda: prefs)
    delivery.outlook = SimpleNamespace(missing=lambda: False, send=lambda mid, mail: sent.append(mail) or {'status': 'accepted'})
    tick = lambda: asyncio.run(delivery._run(lambda: data, NOW))
    assert tick()['p1_email']['status'] == 'dry_run' and sent == []          # switch off: recorded as a dry run, nothing leaves
    assert 'p1_email' not in tick()                                           # and the dry-run ledger does not repeat itself
    prefs['alert_emails_enabled'] = True                                      # the manager ticks the switch
    first = tick()
    assert first['p1_email']['status'] == 'accepted' and len(sent) == 1 and sent[0]['to'] == ['gm@example.com']
    assert sent[0]['subject'].startswith('[ThreadPilot P1]') and 'Hello Wendy' in sent[0]['body']
    second = tick()
    assert 'p1_email' not in second and second['held_back'] == len(first['p1_email']['keys']) and len(sent) == 1
    assert delivery.ledger.kpis(NOW)['delivered_today'] == 1


def test_urgent_emails_wait_for_the_morning_and_the_next_trigger_is_0700():
    """An urgent email at 00:00:00 helps nobody. What becomes urgent overnight is held, unrecorded, and the first check
    from 07:00:00 sends it. Settings shows that moment and offers to jump to two seconds before it."""
    from datetime import datetime, timedelta
    from app.services import alert_policy
    from app.workflow_tools import DataTools
    tools = DataTools(Path(DATA))

    def snapshot_for(day):
        snap, _ = tools.queue_snapshot(datetime(day.year, day.month, day.day, 9, tzinfo=NOW.tzinfo))
        for name in ('orders', 'production_log', 'workshops'):
            snap.setdefault(name, [e.record for e in tools.rows(name + '.csv')])
        snap['today'] = day.isoformat()
        return snap

    def check(at, history=()):
        decisions = alert_policy.gate(alert_policy.detect(snapshot_for(at.date()), at), list(history), at)
        return ({d.alert.key for d in decisions if d.channel == 'email_now'}, [d for d in decisions if d.channel == 'suppressed' and d.reason.startswith('held until 07:00')])

    found = alert_policy.next_trigger(snapshot_for, [], {}, TODAY, NOW.tzinfo)
    assert found['trigger_at'] == TODAY.isoformat() + 'T07:00:00+08:00'
    keys = {i['key'] for i in found['items']}
    assert 'stage_drop:ASSEMBLY' in keys and 1 <= len(keys) <= alert_policy.MAX_P1_PER_DAY
    assert any(i['new_at_this_moment'] for i in found['items']), 'at least one item was not urgent the day before'
    seven = datetime.fromisoformat(found['trigger_at'])
    # the night: nothing is emailed at midnight, at 03:00 or at 06:59:59; the urgent items are held, with the reason
    for night in (seven.replace(hour=0), seven.replace(hour=3), seven - timedelta(seconds=1), seven.replace(hour=22), seven.replace(hour=23, minute=59, second=59)):
        sent, held = check(night)
        assert sent == set() and len(held) >= 1, night
    # the day: from 07:00:00 to 21:59:59 the same items are due
    assert check(seven)[0] == check(seven + timedelta(seconds=1))[0] == check(seven.replace(hour=21, minute=59, second=59))[0] == keys
    # once delivered at 07:00, the next trigger is a later 07:00 with only what is new by then
    history = [{'key': k, 'tier': 'P1', 'score': 100, 'channel': 'email_now', 'sent_at': found['trigger_at'], 'status': 'accepted'} for k in keys]
    later = alert_policy.next_trigger(snapshot_for, history, {}, TODAY, NOW.tzinfo)
    assert later is None or (later['trigger_at'] > found['trigger_at'] and later['trigger_at'].endswith('T07:00:00+08:00') and not ({i['key'] for i in later['items']} & keys))
