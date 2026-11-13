"""Writes the script of the full product demo as plain text, from the recording itself.

    python3 demo/make_demo_script.py --srt ThreadPilot_Demo.srt --duration 285 --out ThreadPilot_Demo_script.txt

For each caption of the recorded video (the .srt gives the real times): the caption, the line to say over it
(demo/prompter_lines.py, the same lines the teleprompter shows) and what is typed or clicked on screen
(demo/demo_timeline_demo_{a,b,c}.json: desk, phone, desk). Run it after every re-recording so the script cannot drift from the video.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prompter_lines  # noqa: E402
from make_prompter import SHORT, clock, srt  # noqa: E402

CHAPTERS = [(0, '07:00 · At the desk: the screen speaks first'), (9, '09:40 · On the floor: a phone, by voice'), (17, '10:30 · Back at the desk: questions'),
            (21, '11:15 · Can we take it?'), (26, '14:30 · Actions with a safety catch'), (32, 'Alerts, rationed'), (33, 'Honesty under pressure'), (37, 'Close')]
SHOWS = [(1, 'Proactive is a dial', 'decision cards, drafted chase-ups, rationed alerts'),
         (4, 'Action tools with confirmation + audit', 'drafted chase-up, core-task chase, watch, Activity Log'),
         (7, 'Concise first, one click to detail', "3-line status, cards, 'Show more', 'i' buttons"),
         (8, 'Scheduled morning briefing', '07:00 briefing on the home screen'),
         (9, 'Used from a phone', 'home screen, chat and Orders page at phone width'),
         (10, 'Voice input', "microphone tapped; 'O R D zero zero five' becomes ORD-005 and is sent"),
         (11, 'Spoken reply', 'the answer is read aloud; speaker button keeps replies on'),
         (13, 'The model does no arithmetic', "'most pieces' computed by a tool over the order book"),
         (15, 'No send without a tap', "a spoken 'send now' waits in the box"),
         (18, 'Judgement tool, inspectable', "'was assembly normal?' + the 'i' on the pulse"),
         (19, "Ask, don't guess", 'TrendCart has six orders, so it asks which'),
         (20, 'Tracing to the rows', "'Show more': planner reading, tool calls, source rows"),
         (22, 'Feasibility with assumptions, not a yes', '800 hoodies in chat + Feasibility page, same figures'),
         (30, 'Watches and alerts, rationed', 'conditional watch; alert policy in Settings'),
         (34, 'Says what the data cannot answer', 'revenue question; ORD-218 not on file'),
         (35, "Checks the manager's premise", "'hasn't moved in a week' true; 'stuck since last week' false")]


def actions(steps):
    """What happens on screen during each caption: [[...], ...] indexed by cue."""
    out, cur = [], None
    for s in steps:
        if s.get('say'):
            cur = []
            out.append(cur)
        if cur is None:
            continue
        if 'goto' in s:
            cur.append('opens ' + {'#/dashboard': 'the home screen', '#/ai': 'the AI workspace', '#/activity': 'the Activity Log',
                                   '#/settings': 'Settings', '#/orders': 'the Orders page'}.get(s['goto'], s['goto']))
        if 'type' in s:
            cur.append(f'types “{s["type"]["text"]}”')
        if 'evaluate' in s and '__voiceSay' in s['evaluate']:
            cur.append('taps the microphone and says “' + json.loads(s['evaluate'].split('=', 1)[1].strip().rstrip(';')) + '”')
        if isinstance(s.get('click'), dict) and s['click'].get('text'):
            cur.append(f'clicks “{s["click"]["text"]}”')
        elif isinstance(s.get('click'), str):
            c = s['click']
            label = ('“Review options” on ORD-029' if 'Review options' in c else '“Analyze expedite impact”' if 'risk-detail' in c
                     else '“Review & send” on ORD-002' if 'ready-draft' in c else 'the “i” on Production pulse' if 'data-info' in c
                     else '“Show more”' if 'tool-steps' in c else 'the Feasibility tab' if 'feasibility"' in c
                     else 'the speaker button (spoken replies on)' if 'voice-replies' in c
                     else '“Compare scenarios”' if 'feasibility-form' in c else 'the first email row' if 'email-activity' in c else None)
            if label and (not cur or cur[-1] != f'clicks {label}'):
                cur.append(f'clicks {label}')
        if 'fill' in s:
            cur.append(f'enters {s["fill"]["value"]}')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--srt', required=True, type=Path)
    ap.add_argument('--duration', required=True, type=float)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    cues = srt(a.srt)
    lines = prompter_lines.DEMO
    acts = [x for part in 'abc' for x in actions(json.loads((HERE / f'demo_timeline_demo_{part}.json').read_text())['steps'])]
    assert len(acts) == len(cues) and lines[-1][1] == len(cues) - 1, 'timeline, captions and spoken lines must describe the same recording'
    spoken = {first: (who, text, last) for first, last, who, text in lines}
    end = lambda i: cues[i + 1]['start'] if i + 1 < len(cues) else a.duration
    W = 72
    out = ['THREADPILOT: FULL PRODUCT DEMO (no slides)', f'Group 19 · Track 1 · DSS5105 · {date.today():%-d %B %Y}',
           f'Length: {clock(a.duration)} (limit 5:00) · file: Video.mp4 in Group19.zip (also ThreadPilot_Demo.mp4)', '=' * W, '',
           'WHAT IT IS',
           'One working day of the general manager, shown entirely in the product: at',
           'the desk (home screen, chat, Feasibility page, Activity Log, Settings) and,',
           'from 09:40, on a phone on the factory floor, by voice. No slides. The header',
           'clock follows the day (07:00, 09:40, 10:30, 11:15, 14:30). Captions are burned',
           'in at the bottom and paced for reading.',
           '',
           'HOW IT WAS RECORDED (say this if asked)',
           'Offline replay: the real interface and engine on the Track 1 records, with the',
           "language model's reading of each message scripted so the recording is",
           'repeatable; nothing is emailed. The phone chapter is the real app in a',
           'phone-sized browser. A recording browser has no microphone or speaker, so',
           'both are simulated: the words "spoken" are fed to the app\'s own voice code,',
           'and the spoken reply is shown as a dark strip of text because the video is',
           'silent. A line under the captions says all of this throughout.',
           'Business date: 1 April 2026.',
           '',
           'TO MAKE IT STRONGER BEFORE SUBMITTING (optional)',
           '  1. Record the voice-over with the SAY lines below (three voices).',
           '  2. Replace 0:56-2:00 with a real phone screen recording, sound on, doing',
           '     the same five steps. That removes the "simulated" caveat.', '', 'CHAPTERS', '']
    for n, (i, title) in enumerate(CHAPTERS):
        stop = cues[CHAPTERS[n + 1][0]]['start'] if n + 1 < len(CHAPTERS) else a.duration
        out.append(f'  {n + 1 if title != "Close" else "—"}  {clock(cues[i]["start"])}-{clock(stop)}  {title}')
    out += ['', 'WHAT THE DEMO SHOWS WELL (Track 1 requirement -> where to look)', '']
    out += [f'  {clock(cues[i]["start"]):>5}  {req:<40} {where}' for i, req, where in SHOWS]
    out += ['', 'VOICES', '']
    spans = {}
    for first, last, who, _ in lines:
        s0, e0 = spans.get(who, (cues[first]['start'], 0))
        spans[who] = (s0, end(last))
    out += [f'  {who:<24} {clock(s)}-{clock(e)}  ({round(e - s)} s)' for who, (s, e) in spans.items()]
    out += ['', '  Say the SAY lines, not the captions: the captions are written for reading.',
            '  ThreadPilot_Demo_prompter.mp4 shows the same lines, filling in at speaking pace.', '',
            '=' * W, 'SCRIPT   [time]  CAPTION on screen  /  SAY aloud  /  what happens on screen', '=' * W]
    chapter = dict(CHAPTERS)
    for i, c in enumerate(cues):
        if i in chapter:
            out += ['', f'--- {chapter[i].upper()} ({clock(c["start"])}) ---']
        out += ['', f'[{clock(c["start"])}-{clock(end(i))}]', f'  CAPTION  {c["text"]}']
        if i in spoken:
            who, text, _ = spoken[i]
            out.append(f'  SAY ({SHORT[who]})  {text}')
        if acts[i]:
            out.append('  ON SCREEN  ' + '; '.join(acts[i]) + '.')
    a.out.write_text('\n'.join(out) + '\n', encoding='utf-8')
    print('wrote', a.out)


if __name__ == '__main__':
    main()
