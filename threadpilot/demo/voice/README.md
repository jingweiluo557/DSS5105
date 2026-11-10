# Voice-over clips (Sprint 3 video) — three voices, about 1½ minutes each

Drop the recorded clips here and run the "Record the presentation video" workflow (Actions tab); the video adapts to
them. Without clips the narration is burned in as captions, which is how the current video is made.

| File | Covers (video time) | Voice | Length |
|---|---|---|---|
| `cover.m4a` | Slide 1, title (0:00–0:06) | Le Wenni (Wendy) | 6 s |
| `objective.m4a` | Slide 2, objective (0:06–0:30) | Le Wenni (Wendy) | 24 s |
| `demo@0.m4a` | Demo, user journey: home screen, expedite review, drafted chase-up sent, briefing, chat to “Show more” (0:30–1:41) | Le Wenni (Wendy) | 71 s |
| `demo@71.m4a` | Demo, 800-hoodie estimate, core task end to end, alert policy, three hard cases (1:41–3:22) | Foo Toon Ming (Matthew) | 101 s |
| `evaluation.m4a` | Slide 3, ground-truth results (3:22–4:00) | Kevin Royce Thomson | 38 s |
| `failures.m4a` | Slide 4, what breaks it, next fixes (4:00–4:27) | Kevin Royce Thomson | 27 s |
| `conclusion.m4a` | Slide 5, achieved and learned (4:27–4:49) | Kevin Royce Thomson | 22 s |

Wendy 101 s · Matthew 101 s · Kevin 87 s (total 4:49).

**Slide clips** set the slide's length (clip + 0.7 s), so keep each within a few seconds of its target to stay under
5:00 (the workflow warns past 4:55).

**Demo clips** are laid over the fixed demo recording: `demo@0` starts with the demo and `demo@71` starts 71 seconds
into it (video 1:41, the caption "11:15 — a customer asks for 800 hoodies by the 25th"). A clip longer than its window
runs over the next part, so keep `demo@0` under 71 s.

**Pace with the teleprompter, not the captions.** The burned-in captions are written to be read and many run at
200–570 words a minute, too fast to say. `Presentation_Group19_prompter.mp4` (and `ThreadPilot_Demo_prompter.mp4` for the
product demo) is a silent, text-only video timed to the real one that scrolls like a teleprompter. The line to say now
sits at the top, its words turning yellow at speaking pace (about 145 words a minute). The next five or six lines are
listed below in grey with the time each one starts, so you can read ahead and decide whether to speed up or slow down.
It also shows who speaks, the clock, the caption the viewer sees, and a handover warning three seconds before the
speaker changes. Start it, start recording at the clip's start time, and keep level with the yellow. The lines are in `demo/prompter_lines.py`; rebuild with `demo/make_prompter.py`
(see its docstring), which also writes the lines as a text script and warns when a line is too fast for its window.

Lines: the "Sprint 3 video script" doc, or each slide's speaker notes. `.m4a`, `.mp3`, `.wav`, `.aac` or `.ogg` all
work. Record with the phone's voice memo app or QuickTime, export, rename exactly as above, commit, push, run the
workflow (set "burn slide captions" off if you want clean slides under the voice).
