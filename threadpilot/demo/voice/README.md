# Voice-over clips (Sprint 3 video) — three voices, about 1½ minutes each

Drop the recorded clips here and run the "Record the presentation video" workflow (Actions tab); the video adapts to
them. Without clips the narration is burned in as captions, which is how the current video is made.

| File | Covers (video time) | Voice | Length |
|---|---|---|---|
| `cover.m4a` | Slide 1, title (0:00–0:06) | Kevin Royce Thomson | 6 s |
| `objective.m4a` | Slide 2, objective (0:06–0:30) | Kevin Royce Thomson | 24 s |
| `demo@0.m4a` | Demo, user journey: home screen to the 800-hoodie estimate (0:30–1:39) | Kevin Royce Thomson | 69 s |
| `demo@69.m4a` | Demo, Feasibility page, core task, three hard cases (1:39–3:04) | Foo Toon Ming (Matthew) | 85 s |
| `evaluation.m4a` | Slide 3, ground-truth results (3:04–3:40) | Le Wenni (Wendy) | 36 s |
| `failures.m4a` | Slide 4, what breaks it, next fixes (3:40–4:10) | Le Wenni (Wendy) | 30 s |
| `conclusion.m4a` | Slide 5, achieved and learned (4:10–4:35) | Le Wenni (Wendy) | 25 s |

Kevin 99 s · Matthew 85 s · Wendy 91 s.

**Slide clips** set the slide's length (clip + 0.7 s), so keep each within a few seconds of its target to stay under
5:00 (the workflow warns past 4:55).

**Demo clips** are laid over the fixed demo recording: `demo@0` starts with the demo and `demo@69` starts 69 seconds
into it (video 1:39, the caption "The Feasibility page runs the same simulation…"). Easiest way to stay in sync: play
the current `Presentation_Group19.mp4` muted, start recording at the clip's start time, and read each caption as it
appears. A clip longer than its window runs over the next part, so keep `demo@0` under 69 s.

Lines: the "Sprint 3 video script" doc, or each slide's speaker notes. `.m4a`, `.mp3`, `.wav`, `.aac` or `.ogg` all
work. Record with the phone's voice memo app or QuickTime, export, rename exactly as above, commit, push, run the
workflow (set "burn slide captions" off if you want clean slides under the voice).
