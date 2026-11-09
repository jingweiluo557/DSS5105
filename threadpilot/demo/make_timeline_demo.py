"""Writes demo/demo_timeline_demo.json: the full product demo (about 4.5 minutes, no slides), Video.mp4 in Group19.zip.

One working day of the general manager, in six chapters, each caption naming what the system does well:
  1. 07:00  the home screen speaks first: decisions, an expedite simulation, chase-ups drafted before she asks,
            the "i" explanation of "normal", the morning briefing;
  2. 09:40  questions on the floor: discovery, the normal-range judgement, a vague question it asks about instead of
            guessing, the tool calls and source rows behind an answer, two orders in one chat, a total it refuses to add;
  3. 11:15  a feasibility estimate with its assumptions, in the chat and on the Feasibility page;
  4. 14:30  actions with a safety catch: the claim checked, preview, confirm, a conditional watch, the Activity Log;
  5.        alerts that speak first, rationed by a written policy;
  6.        honesty under pressure: no price data, a wrong premise, a description with no ID, an order not on file.

Edit the beats here and re-run:  python3 demo/make_timeline_demo.py
Offline replay: the real frontend and engine over the Track 1 CSVs; the language model's reading of each message is
scripted in demo/replay_server.py (SCRIPT); nothing is emailed. Record with REPLAY_STEP_PACE=0.35 and --compress-waits 4.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
base = json.loads((HERE / 'demo_timeline_final.json').read_text())
T = '[data-form="chat"] textarea'
B = '[data-form="chat"] button[type="submit"]'
steps, t = [], 0.0


def at(dt):
    global t
    t = round(t + dt, 1)
    return t


def say(dt, text):
    steps.append({'at': at(dt), 'say': text})


def do(dt, caption=None, **action):
    steps.append({'at': at(dt), **action, **({'say': caption} if caption else {})})


def ask(dt, text, cps=40, real=False):
    extra = {'real': True} if real else {}
    steps.append({'at': at(dt), 'type': {'into': T, 'text': text, 'cps': cps}, **extra})
    steps.append({'at': at(len(text) / cps + 0.3), 'click': B, **extra})
    steps.append({'at': at(0.1), 'waitAnswer': True, **extra})


# ---------------------------------------------------------------- 1. 07:00, the screen speaks first
do(0, 'ThreadPilot, the general manager’s co-pilot. One working day at a knitwear factory, on its own records: 1 April 2026.', goto='#/dashboard')
say(4.0, '07:00 · Before she asks anything, the day is on one screen: RED, 8 orders overdue, assembly below normal for 6 days, 3 decisions.')
do(0.4, scroll={'to': 'article.decision >> nth=0'})
say(3.6, 'Each decision has one button. “Review options” runs the queue simulation for ORD-029, which will miss 1 April.')
do(1.2, click='article.decision >> nth=1 >> text=Review options')
do(1.6, click='aside.risk-detail button >> nth=0')
do(0.4, waitFor={'text': 'Expedite review', 'timeout': 20000})
say(0.4, 'Moving ORD-029 up saves it 5 days but makes 6 other orders 11 days later in total, so it recommends keeping the current order.')
do(4.4, click={'text': 'Close'})
do(0.6, goto='#/dashboard')
do(0.8, 'Drafted before she asks: the two stalled orders already have a chase-up, written from the records, not by the model.', scroll={'to': 'section.ready-drafts'})
do(3.8, click='section.ready-drafts [data-action="ready-draft"] >> nth=0')
do(0.1, waitAnswer=True)
say(0.4, '“Review & send” opens the preview: to washing, 9 days idle, 3 days overdue. She reads it and confirms.')
do(4.0, click={'text': 'Confirm send'}, optional=True, real=True)
do(0.4, waitAnswer=True, optional=True, real=True)
say(0.4, 'Sent and logged; ORD-002 leaves the list. Nothing went out before her click.')
do(2.4, click='[aria-label="Close AI drawer"]', optional=True)
do(2.0, scroll={'to': 'section.home-pulse'})
say(0.2, 'Every chart has an “i”: what it shows, how to read it, and why it is computed that way.')
do(0.8, click='section.home-pulse [data-info="pulse"]')
say(1.0, '“Normal” is the previous 8 same weekdays (Sundays are closed): measured on this factory, it cut false alerts from 0.67 to 0.1 a month.')
do(3.6, press='Escape')
do(0.4, 'The 07:00 briefing is written on a schedule: yesterday, what is at risk, what to decide, each point with its records.', scroll={'to': 'section.home-briefing'})
do(3.2, click={'text': 'Open the full briefing'})
do(2.0, scroll={'by': 340})
# ---------------------------------------------------------------- 2. 09:40, questions on the floor
do(2.2, '09:40 · On the floor, she asks in her own words. “Did anything go wrong yesterday?”', goto='#/ai')
ask(0.8, 'Did anything go wrong yesterday?')
say(0.6, 'A discovery tool ranks 34 findings by tier and score, so five make the page and the rest wait: the assembly drop first.')
ask(3.6, 'Was yesterday’s assembly output normal?')
say(0.6, 'A judgement tool with a written definition: 455 pieces against 687–807 for the previous eight Tuesdays, 39% below.')
ask(3.6, 'How is the TrendCart order doing?')
say(0.6, 'A vague question: TrendCart has six active orders, so it asks instead of guessing.')
ask(2.8, 'The scarf one.')
say(0.6, 'Only one is a scarf: ORD-005, at knitting, due 20 April.')
do(2.4, click='details.tool-steps >> nth=-1 >> summary', optional=True)
say(0.6, '“Show more”: the planner’s reading, each tool with its arguments, and the exact rows the answer came from.')
do(3.8, click='details.tool-steps >> nth=-1 >> summary', optional=True)
ask(0.6, 'What about ORD-120?')
say(0.6, 'A second order in the same chat: ORD-120, 1,500 vests at assembly, due 17 March.')
ask(2.6, 'Is the scarf one late?')
say(0.6, 'It remembers the chat: “the scarf one” is ORD-005, back from two answers ago. Not late yet, but the queue projects it 6 working days late, and it says why.')
ask(4.2, 'What was the factory’s total output yesterday?')
say(0.6, 'A total that must not exist: the four stages are steps on the same pieces, so it lists them and refuses to add them up.')
# ---------------------------------------------------------------- 3. 11:15, can we take it?
say(4.4, '11:15 · A customer wants 800 hoodies by the 25th.')
ask(0.6, 'Can we take 800 hoodies by the 25th?')
say(0.6, 'It asks the one thing that changes the answer: ready at the factory, or delivered?')
ask(2.8, 'Delivered to the customer.')
say(0.6, 'An estimate, not a yes: the queue’s finish date, the on-time chance, the bottleneck, outside workshops that could take it.')
do(5.0, 'The Feasibility page runs the same tool over the whole queue.', click='nav.workspace-tools a[href="#/feasibility"]')
do(1.6, fill={'into': '#feasibility-form input[name="qty"]', 'value': '800'})
do(1.0, fill={'into': '#feasibility-form input[name="due"]', 'value': '2026-04-25'})
do(1.0, click='#feasibility-form button[type="submit"]')
do(0.6, waitFor={'text': 'with usual new orders', 'timeout': 20000})
say(0.6, 'Our own queue finishes 30 April, after the 25th; an eligible outside workshop could make it in time.')
do(4.6, 'Why: queued work plus this order is over capacity at the later stages before the 25th.', scroll={'to': '#capacity-picture'})
# ---------------------------------------------------------------- 4. 14:30, actions with a safety catch
do(4.4, '14:30 · The core task: chase a stalled order, typed the way it is said on the floor.', goto='#/ai')
ask(1.0, 'ORD 5 hasn’t moved in a week, chase knitting', cps=34)
say(0.6, 'It checks the claim against the record first (last activity 24 March, 8 days: true), then drafts to knitting.')
ask(4.2, 'Preview draft 1')
say(0.6, 'Preview first. Nothing is sent until the manager confirms this exact draft.')
do(3.4, click={'text': 'Confirm send'}, optional=True, real=True)
do(0.4, waitAnswer=True, optional=True, real=True)
say(0.6, 'Sent from the manager’s own mailbox.')
ask(2.2, 'Remind me tmrw 10am if knitting doesn’t reply', cps=34)
say(0.6, 'A standing watch, not a note: at 10:00 tomorrow the server checks, and notifies only if no reply was recorded.')
ask(3.8, 'Confirm.', real=True)
do(0.8, 'Every action is logged: the Activity Log shows both chase-ups with recipient, orders and subject.', goto='#/activity')
do(0.6, waitFor={'text': 'Order chase-up', 'timeout': 15000}, optional=True)
do(3.6, click='#email-activity details >> nth=0 >> summary', optional=True)
# ---------------------------------------------------------------- 5. alerts, rationed
do(2.8, 'It also speaks first, but rationed: an alert email only for a decision needed today, at most 3 a day, never the same item twice in 24 hours.', goto='#/settings')
do(1.0, scroll={'to': '[data-email="test-alert"]'})
# ---------------------------------------------------------------- 6. honesty under pressure
do(4.4, 'Honesty under pressure. A question the data cannot answer:', goto='#/ai')
ask(0.8, 'What revenue did the TrendCart orders bring in this quarter?')
say(0.6, 'No prices in the records, so no revenue figure. It says what it can answer instead.')
ask(3.6, 'Chase ord 29, stuck at washing since last wk', cps=34)
say(0.6, 'A wrong premise: the record says ORD-029 moved today. It says so, and asks before writing anything.')
ask(4.2, 'Chase the order with 1500 tops', cps=34)
say(0.6, 'No order ID, only a description: three orders match, so it lists them instead of picking one.')
ask(3.0, 'The vest one.')
say(0.6, '“The vest one” narrows that list to ORD-120 and drafts to assembly. Still nothing sent.')
ask(3.6, 'Is ORD-218 shipped?')
say(0.6, 'Not in the records, and it says so. It never invents an order, a stage or a number.')
say(4.2, 'Every number comes from a tool with its rows · it asks instead of guessing · it says what the data cannot answer · nothing leaves without a confirmed preview.')
do(5.2, hold=0.8)

timeline = {'_comment': __doc__.strip().splitlines()[0] + ' Generated by demo/make_timeline_demo.py; record with REPLAY_STEP_PACE=0.35.',
            'viewport': {'width': 1280, 'height': 648, 'scale': 1.5}, 'captions': base['captions'], 'bandHeight': base['bandHeight'], 'steps': steps}
(HERE / 'demo_timeline_demo.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=1))
print(f'planned {t:.1f} s before model waits, {len(steps)} steps -> demo/demo_timeline_demo.json')
