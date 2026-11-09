"""Writes demo/demo_timeline_sprint3.json: the Sprint 3 video demo (about 3 minutes).

Order (the brief): the user journey first, the way a general manager uses ThreadPilot through the day (including the
expedite decision on a home card, the chase-ups drafted before she asks, and the alert policy); then the core task
end to end on realistic input (chase a stalled order: claim checked against the record, draft, preview, confirm,
conditional reminder); then three hard cases (a false premise, a description with no order ID, an order not on file).

Edit the beats here and re-run:  python3 demo/make_timeline_sprint3.py
Offline replay: the real frontend and engine over the Track 1 CSVs; the language model's reading of each message is
scripted in demo/replay_server.py (SCRIPT); nothing is emailed. Live mode records the deployed site instead.
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


# ---------------------------------------------------------------- 1. the user journey
do(0, 'User journey. 07:00 — the general manager opens ThreadPilot before walking the floor. The day is already on one screen.', goto='#/dashboard')
say(3.4, 'RED: 8 orders overdue, assembly below its normal range for 6 days, 3 decisions waiting. Nothing here was asked for.')
do(0.4, scroll={'to': 'article.decision >> nth=0'})
say(3.2, 'A decision card: ORD-029 will miss 1 April. “Review options” runs the queue simulation.')
do(1.2, click='article.decision >> nth=1 >> text=Review options')
do(1.6, click='aside.risk-detail button >> nth=0')
do(0.4, waitFor={'text': 'Expedite review', 'timeout': 20000})
say(0.4, 'Moving ORD-029 up saves it 5 days but makes 6 other orders 11 days later in total, so it recommends keeping the current order.')
do(4.4, click={'text': 'Close'})
do(0.6, goto='#/dashboard')
do(0.8, 'It also drafts before she asks: both stalled orders already have a chase-up, written from the records.', scroll={'to': 'section.ready-drafts'})
do(3.6, click='section.ready-drafts [data-action="ready-draft"] >> nth=0')
do(0.1, waitAnswer=True)
say(0.4, '“Review & send” opens the preview: to washing, 9 days idle, 3 days overdue. She checks it and confirms.')
do(4.4, click={'text': 'Confirm send'}, optional=True, real=True)
do(0.4, waitAnswer=True, optional=True, real=True)
say(0.4, 'Sent and logged; ORD-002 leaves the list. Nothing went out before her click.')
do(2.4, click='[aria-label="Close AI drawer"]', optional=True)
do(2.2, scroll={'to': 'section.home-pulse'})
say(0.2, 'Every chart has an “i”: what it shows and why it is computed that way.')
do(0.8, click='section.home-pulse [data-info="pulse"]')
say(1.0, '“Normal” = the previous 8 same weekdays: on this factory that cut false alerts from 0.67 to 0.1 a month.')
do(3.4, press='Escape')
do(0.4, 'The morning briefing, written at 07:00, each point with its supporting records.', scroll={'to': 'section.home-briefing'})
do(3.0, click={'text': 'Open the full briefing'})
do(2.2, scroll={'by': 340})
do(2.0, '09:40 — on the floor, she asks in her own words.', goto='#/ai')
ask(0.8, 'How is the TrendCart order doing?')
say(0.6, 'TrendCart has six active orders, so it asks instead of guessing.')
ask(2.8, 'The scarf one.')
say(0.6, 'ORD-005: 500 scarves at knitting, due 20 April. Each answer shows the tool calls behind it.')
do(2.8, click='details.tool-steps >> nth=-1 >> summary', optional=True)
say(0.6, '“Show more”: the planner’s reading, each tool with its arguments, and the records it used.')
do(3.8, click='details.tool-steps >> nth=-1 >> summary', optional=True)
say(0.6, '11:15 — a customer asks for 800 hoodies by the 25th.')
ask(0.6, 'Can we take 800 hoodies by the 25th?')
say(0.6, 'It asks the one thing that changes the answer: ready at the factory, or delivered?')
ask(2.8, 'Delivered to the customer.')
say(0.6, 'An estimate with its assumptions: the queue’s finish date, the on-time chance, the bottleneck, outside workshops that could take it. Not a promise.')
# ---------------------------------------------------------------- 2. the core task, end to end
say(5.4, 'Core task, end to end. 14:30 — the same chase in her own words, typed the way it is said on the floor.')
ask(1.0, 'ORD 5 hasn’t moved in a week, chase knitting', cps=34)
say(0.6, 'It checks the claim against the record first — last activity 24 March, 8 days: true — then drafts to knitting.')
ask(4.2, 'Preview draft 1')
say(0.6, 'Preview first. Nothing is sent until the manager confirms this exact draft.')
do(3.4, click={'text': 'Confirm send'}, optional=True, real=True)
do(0.4, waitAnswer=True, optional=True, real=True)
say(0.6, 'Sent from the manager’s mailbox, and logged.')
ask(2.4, 'Remind me tmrw 10am if knitting doesn’t reply', cps=34)
say(0.6, 'A conditional watch: at 10:00 tomorrow it notifies only if no reply has been recorded.')
ask(3.6, 'Confirm.', real=True)
do(0.8, 'It also speaks first: an alert email only for a decision needed today — at most 3 a day, never the same item twice in 24 hours.', goto='#/settings')
do(1.0, scroll={'to': '[data-email="test-alert"]'})
do(4.0, goto='#/ai')
# ---------------------------------------------------------------- 3. hard cases
say(1.0, 'Hard case 1 — a wrong premise: ORD-029 “stuck since last week”.')
ask(0.8, 'Chase ord 29, stuck at washing since last wk', cps=34)
say(0.6, 'The record says it moved today. It says so, and asks before writing anything.')
say(4.4, 'Hard case 2 — no order ID, only a description.')
ask(0.6, 'Chase the order with 1500 tops', cps=34)
say(0.6, 'Three orders match, so it lists them instead of picking one.')
ask(3.0, 'The vest one.')
say(0.6, '“The vest one” narrows that list to ORD-120 and drafts to assembly. Nothing sent.')
say(4.2, 'Hard case 3 — an order that does not exist.')
ask(0.6, 'Is ORD-218 shipped?')
say(0.6, 'Not in the records — and it says so. It does not invent an order, a stage or a number.')
do(4.2, hold=0.8)

timeline = {'_comment': __doc__.strip().splitlines()[0] + ' Generated by demo/make_timeline_sprint3.py; record with REPLAY_STEP_PACE=0.35.',
            # 1280x648 CSS px at 1.5x = 1920x972 video: the interface reads at projector size (1920 CSS px made text too small)
            'viewport': {'width': 1280, 'height': 648, 'scale': 1.5}, 'captions': base['captions'], 'bandHeight': base['bandHeight'], 'steps': steps}
(HERE / 'demo_timeline_sprint3.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=1))
print(f'planned {t:.1f} s before model waits, {len(steps)} steps -> demo/demo_timeline_sprint3.json')
