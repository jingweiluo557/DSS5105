# Voice-over clips

Drop the recorded narration here and run the "Record the presentation video" workflow; the video adapts to the clips.

| File | Used for |
|---|---|
| `cover.m4a`, `change.m4a`, `architecture.m4a`, `tools.m4a`, `validation.m4a`, `hardcases.m4a`, `interface.m4a`, `next.m4a` | one clip per slide (named after the slide id in `../slides/deck.json`); each slide stays on screen for as long as its clip plus a 0.7 s pause, so the timing in the notes no longer matters |
| `slides.m4a` | one take for all eight slides instead, laid over the slides at the notes' timing (0:00–2:50) |
| `demo.m4a` | optional narration over the demo (the subtitles stay burned in) |

`.m4a`, `.mp3`, `.wav`, `.aac` or `.ogg` all work. A slide without a clip keeps its notes' timing, silent. Read the lines from the "Sprint 2 video script" doc; keep the whole run under 5:00 (the workflow warns past 4:55).

Record with the phone's voice memo app or QuickTime, export, rename, commit, push.
