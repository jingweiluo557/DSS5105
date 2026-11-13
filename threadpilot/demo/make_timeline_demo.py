"""Writes the three timelines of the full product demo (under 5 minutes, no slides), Video.mp4 in Group19.zip:
demo_timeline_demo_a.json (desk, 07:00), demo_timeline_demo_b.json (phone, voice in and voice out, 09:40) and
demo_timeline_demo_c.json (desk, the rest of the day). demo/assemble_demo.py records nothing: it joins the three recordings,
puts the phone recording in a phone frame on the same 1920x1080 canvas, and burns the captions into the band.

Version of 14 Nov: the phone chapter is new (voice input, spoken replies, phone layout); to stay under five minutes the
desk chapters lost the expedite close-up of the briefing page, the second order in one chat, the factory-total refusal,
the side-by-side scenario cards and the "1500 tops" hard case (all still in the Sprint 3 presentation video).

One working day of the general manager, in six chapters, each caption naming what the system does well:
  1. 07:00  the home screen speaks first: decisions, an expedite simulation, chase-ups drafted before she asks,
            the "i" explanation of "normal", the morning briefing;
  2. 09:40  questions on the floor: discovery, the normal-range judgement, a vague question it asks about instead of
            guessing, the tool calls and source rows behind an answer, two orders in one chat, a total it refuses to add;
  3. 11:15  a feasibility estimate with its assumptions, in the chat and on the Feasibility page (same figures);
  4. 14:30  actions with a safety catch: the claim checked, preview, confirm, a conditional watch, the Activity Log;
  5.        alerts that speak first, rationed by a written policy;
  6.        honesty under pressure: no price data, a wrong premise, a description with no ID, an order not on file.

Edit the beats here and re-run:  python3 demo/make_timeline_demo.py
Captions are paced for reading: a caption stays up for at least its word count / READ_WPS seconds (3 s minimum), and
later steps move back to make room. The header clock follows the story (the replay server's /__replay/clock).

Offline replay: the real frontend and engine over the Track 1 CSVs; the language model's reading of each message is
scripted in demo/replay_server.py (SCRIPT); nothing is emailed. Record with
  REPLAY_NOW=2026-04-01T07:00:00+08:00 REPLAY_STEP_PACE=0.35 python3 demo/replay_server.py 8765
  node demo/record_demo.cjs --timeline demo/demo_timeline_demo.json --out dist/demo --compress-waits 4 --no-wait-tag \\
       --badge "Offline replay · real interface and engine on the factory records · the model's reading of each message is scripted · no real email"
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
base = json.loads((HERE / 'demo_timeline_final.json').read_text())
T = '[data-form="chat"] textarea'
B = '[data-form="chat"] button[type="submit"]'
READ_WPS = 3.6                     # captions are read, not spoken: about 200 words a minute
steps, t = [], 0.0
_cap = {'at': 0.0, 'need': 0.0}
parts = {}


def part(name):
    """Close the current part and start the next: each part is its own recording, so its clock starts at zero."""
    global steps, t
    steps, t = [], 0.0
    _cap.update(at=0.0, need=0.0)
    parts[name] = steps


def at(dt):
    global t
    t = round(t + dt, 1)
    return t


def _caption(text):
    """Called just before a caption is placed at t: hold the previous caption long enough to be read."""
    global t
    t = round(max(t, _cap['at'] + _cap['need']), 1)
    _cap.update(at=t, need=max(3.0, len(text.split()) / READ_WPS))


def say(dt, text):
    at(dt)
    _caption(text)
    steps.append({'at': t, 'say': text})


def do(dt, caption=None, **action):
    at(dt)
    if caption:
        _caption(caption)
    steps.append({'at': t, **action, **({'say': caption} if caption else {})})


def ask(dt, text, cps=40, real=False):
    extra = {'real': True} if real else {}
    steps.append({'at': at(dt), 'type': {'into': T, 'text': text, 'cps': cps}, **extra})
    steps.append({'at': at(len(text) / cps + 0.3), 'click': B, **extra})
    steps.append({'at': at(0.1), 'waitAnswer': True, **extra})


def clock(hhmm):
    """Move the replay's business clock (same day) and refresh the header."""
    do(0.2, evaluate=f"await fetch('/__replay/clock?t={hhmm}'); const r = await fetch('/api/email/clock', {{cache: 'no-store'}}); "
                     "window.threadpilotClock = await r.json(); window.threadpilotClockAnchor = performance.now();")


MIC = '[data-form="chat"] [data-action="voice"]'


def speak(dt, words, caption=None, wait=True):
    """The manager says `words` into the phone: set the stand-in microphone, tap the button, let the words arrive."""
    do(dt, caption, evaluate=f"window.__voiceSay = {json.dumps(words)};")
    do(0.3, click=MIC)
    at(len(words.split()) / 2.8 + 1.0)
    if wait:
        steps.append({'at': at(0.1), 'waitAnswer': True})


# ---------------------------------------------------------------- A. 07:00, at the desk: the screen speaks first
part('a')
do(0, 'ThreadPilot, the general manager’s co-pilot. One working day at a knitwear factory, on its own records: 1 April 2026.', goto='#/dashboard')
say(4.0, '07:00 · Before she asks, the day is on one screen: RED, 8 overdue, assembly below normal for 6 days, 3 decisions.')
do(0.4, scroll={'to': 'article.decision >> nth=0'})
say(3.6, 'Each decision has one button. “Review options” runs the queue simulation for ORD-029, which will miss today.')
do(1.2, click='article.decision >> nth=1 >> text=Review options')
do(1.6, click='aside.risk-detail button >> nth=0')
do(0.4, waitFor={'text': 'Expedite review', 'timeout': 20000})
say(0.4, 'Moving ORD-029 up saves it 5 days but adds 11 to six other orders, so it recommends keeping the current order.')
do(5.6, click={'text': 'Close'})
do(0.6, goto='#/dashboard')
do(0.8, 'Drafted before she asks: the two stalled orders already have a chase-up, written from the records.', scroll={'to': 'section.ready-drafts'})
do(4.4, click='section.ready-drafts [data-action="ready-draft"] >> nth=0')
do(0.1, waitAnswer=True)
say(0.4, '“Review & send” opens the preview: to washing, 9 days idle, 3 days overdue. She reads it and confirms.')
do(4.8, click={'text': 'Confirm send'}, optional=True, real=True)
do(0.4, waitAnswer=True, optional=True, real=True)
say(0.4, 'Sent and logged. Nothing went out before her click.')
do(3.0, click='[aria-label="Close AI drawer"]', optional=True)
do(1.0, scroll={'to': 'section.home-pulse'})
say(0.4, 'Every chart has an “i”. “Normal” means the previous 8 same weekdays, which cut false alerts from 0.67 to 0.1 a month.')
do(0.8, click='section.home-pulse [data-info="pulse"]')
do(5.6, press='Escape')
do(0.4, 'The 07:00 briefing is written on a schedule: yesterday, what is at risk, what to decide.', scroll={'to': 'section.home-briefing'})
do(4.4, hold=0.2)

# ---------------------------------------------------------------- B. 09:40, on the floor: a phone, by voice
part('b')
do(0, '09:40 · On the factory floor she has a phone, not a desk. The same home screen fits it.', goto='#/dashboard')
clock('09:40')
do(1.6, scroll={'by': 520})
do(2.4, goto='#/ai')
say(0.6, 'She taps the microphone and speaks. (The app is the real one; this recording simulates the microphone and speaker.)')
speak(4.2, 'where is o r d zero zero five')
say(0.4, 'Spoken “O R D zero zero five” became ORD-005 and was sent. A spoken question gets a spoken answer.')
do(5.6, 'The speaker button keeps spoken replies on for every answer, typed or spoken.', click='[data-action="voice-replies"] >> nth=0')
speak(3.4, 'which customer has the most pieces in progress')
say(0.4, 'A “most” question is computed from the order book, not guessed: Northwind Apparel, 8,000 pieces, and it says so aloud.')
speak(6.4, 'chase washing on o r d zero eight three')
say(0.4, 'Actions work by voice too: a draft to washing about ORD-083. Still only a draft.')
speak(4.6, 'send now', wait=False)
say(0.6, 'But a spoken “send now” is never sent. It waits in the box for a tap, so a misheard word cannot send an email.')
do(6.6, 'Every page fits the phone: wide tables scroll inside their card, buttons are thumb-sized.', goto='#/orders')
do(2.0, scroll={'by': 380})
do(2.6, hold=0.2)

# ---------------------------------------------------------------- C. back at the desk
part('c')
do(0, goto='#/ai')
clock('10:30')
say(0.4, '10:30 · Back at the desk. “Was yesterday’s assembly output normal?”')
ask(0.6, 'Was yesterday’s assembly output normal?')
say(0.6, 'A judgement tool with a written definition: 455 pieces against 687–807 for the previous eight Tuesdays, 39% below.')
ask(3.6, 'How is the TrendCart order doing?')
say(0.6, 'A vague question: TrendCart has six active orders, so it asks instead of guessing.')
ask(2.8, 'The scarf one.')
say(0.6, 'Only one is a scarf: ORD-005. “Show more” lists the planner’s reading, each tool call and the rows behind the answer.')
do(1.6, click='details.tool-steps >> nth=-1 >> summary', optional=True)
do(4.6, click='details.tool-steps >> nth=-1 >> summary', optional=True)
# 11:15, can we take it?
clock('11:15')
say(0.4, '11:15 · A customer wants 800 hoodies by the 25th.')
ask(0.6, 'Can we take 800 hoodies by the 25th?')
say(0.6, 'It asks the one thing that changes the answer: ready at the factory, or delivered?')
ask(2.8, 'Ready at the factory.')
say(0.6, 'An estimate, not a yes: unlikely. The queue finishes 30 April; it names the bottleneck and the outside workshops.')
do(5.6, 'The Feasibility page runs the same tool over the whole queue and shows why.', click='nav.workspace-tools a[href="#/feasibility"]')
do(1.4, fill={'into': '#feasibility-form input[name="qty"]', 'value': '800'})
do(0.9, fill={'into': '#feasibility-form input[name="due"]', 'value': '2026-04-25'})
do(0.9, click='#feasibility-form button[type="submit"]')
do(0.6, waitFor={'text': 'with usual new orders', 'timeout': 20000})
do(0.6, 'The same figures as the chat: 30 April, five days late, because the later stages are over capacity before the 25th.', scroll={'to': '#capacity-picture'})
# 14:30, actions with a safety catch
do(5.8, goto='#/ai')
clock('14:30')
say(0.4, '14:30 · The core task: chase a stalled order, typed the way it is said on the floor.')
ask(1.0, 'ORD 5 hasn’t moved in a week, chase knitting', cps=34)
say(0.6, 'It checks the claim against the record first (last activity 24 March, 8 days: true), then drafts to knitting.')
ask(4.6, 'Preview draft 1')
say(0.6, 'Preview first. Nothing is sent until the manager confirms this exact draft.')
do(3.6, click={'text': 'Confirm send'}, optional=True, real=True)
do(0.4, waitAnswer=True, optional=True, real=True)
say(0.6, 'Confirmed and sent. On the live system it leaves from the manager’s own mailbox.')
ask(2.0, 'Remind me tmrw 10am if knitting doesn’t reply', cps=34)
say(0.6, 'A standing watch: at 10:00 tomorrow the server checks, and notifies only if no reply was recorded.')
ask(3.8, 'Confirm.', real=True)
do(1.4, 'Every action is logged, with recipient, orders and subject.', goto='#/activity')
do(0.6, waitFor={'text': 'Order chase-up', 'timeout': 15000}, optional=True)
do(1.6, click='#email-activity details >> nth=0 >> summary', optional=True)
# alerts, rationed
do(2.6, 'It also speaks first, but rationed: an alert only for a decision needed today, at most 3 a day.', goto='#/settings')
do(1.0, scroll={'to': '[data-email="test-alert"]'})
# honesty under pressure
do(4.4, 'Honesty under pressure. A question the data cannot answer:', goto='#/ai')
ask(0.6, 'What revenue did the TrendCart orders bring in this quarter?', cps=55)
say(0.6, 'No prices in the records, so no revenue figure. It says what it can answer instead.')
ask(3.0, 'Chase ord 29, stuck at washing since last wk', cps=40)
say(0.6, 'A wrong premise: the record says ORD-029 moved today. It says so, and asks before writing anything.')
ask(3.4, 'Is ORD-218 shipped?')
say(0.6, 'Not in the records, and it says so. It never invents an order, a stage or a number.')
say(4.2, 'Every number comes from a tool with its rows · it asks instead of guessing · by voice or by hand, nothing leaves without a confirmed preview.')
do(7.0, hold=0.4)

doc = __doc__.strip().splitlines()[0]
views = {'a': {'width': 1280, 'height': 648, 'scale': 1.5}, 'b': {'width': 414, 'height': 720, 'scale': 2}, 'c': {'width': 1280, 'height': 648, 'scale': 1.5}}
total = 0.0
for name, part_steps in parts.items():
    timeline = {'_comment': doc + f' Part {name.upper()}. Generated by demo/make_timeline_demo.py; record with REPLAY_STEP_PACE=0.35.',
                'viewport': views[name], 'captionTop': -1, 'steps': part_steps}
    if name == 'b':
        timeline['initScript'] = 'voice_standin.js'
    (HERE / f'demo_timeline_demo_{name}.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=1))
    total += part_steps[-1]['at']
    print(f"part {name}: planned {part_steps[-1]['at']:.1f} s before waits, {len(part_steps)} steps")
print(f'planned {total:.1f} s in all')
