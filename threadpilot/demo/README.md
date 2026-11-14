# Scripted demo recording

`record_demo.cjs` drives the site through `demo_timeline.json` on a fixed timeline, draws a visible cursor that glides to every target with a ripple on each click, shows the narration as a caption bar, records the run as a video and writes the captions as an `.srt` with the real timestamps. It is the demo of the Sprint 2 video ("one general manager's day", about 2:22: the 07:00 briefing, an order question, feasibility in the chat and on the Feasibility page, a chase-up, a watch, and a question the data cannot answer), recorded as a 1920 × 1080 desktop video: the app fills 1920 × 972 and the captions sit in a 108 px band underneath, so nothing covers the page.

## Run it without installing anything: GitHub Actions

Two modes. **offline** (default): the runner starts `demo/replay_server.py`, the real frontend and the real workflow engine over the CSV seeds with a scripted planner in place of the model (the same classifications the evaluation uses for the demo's questions); every tool, rule, preview and watch is real, nothing is sent, and no secret or deploy is needed. **live**: records the deployed site through the model; needs the deploy and the `THREADPILOT_ACCESS_KEY` secret.

Actions tab → **Record the presentation video** → **Run workflow**. A GitHub runner renders the slides (`demo/slides`, each held for the seconds in its speaker notes), records the demo on the deployed site, joins the two and uploads `presentation-video` as an artifact on the run page: `presentation.mp4` (1920 × 1080, slides then demo, under 5 minutes), `presentation.srt` (the whole narration), `slides.mp4`/`slides.srt`, the slide PNGs and `demo_final.mp4`. One-time setup: add the workspace access key as the repository secret `THREADPILOT_ACCESS_KEY` (Settings → Secrets and variables → Actions → New repository secret). The workflow's inputs: the site URL, `dry_run` (on by default: leaves out the send and the watch confirmation), the speed-up factor, the timeline file, `include_demo` (off = slides only, needs no secret) and `burn_slide_captions` (off by default: the slides are clean under the recorded voice-over; on = the narration appears as captions on the slides).

**Voice-over**: record one clip per slide, name them after the slide ids and commit them to `demo/voice/` (see `demo/voice/README.md`); each slide then lasts as long as its clip, and the audio is laid under the video. The demo keeps its burned subtitles; `demo.m4a` adds narration over it if wanted.

## The slides

`demo/slides/` holds the deck as files (`deck.json`, one HTML per slide, `assets/`), the same content as the Claude Slides artifact. `render_slides.cjs` turns them into 1920 × 1080 PNGs; `assemble_video.cjs` holds each for the duration in its speaker note (`<aside>0:06–0:34 · [Presenter] …`), cross-fades between them, and appends the demo. To change timing or wording, edit the HTML (the `<aside>` is the narration and the timing). To use a deck edited on the Slides page instead, export it as PDF to `demo/slides/deck.pdf`: the pages are then used in place of the HTML, and the notes still come from the HTML.

The deck has six slides in the order the brief asks for: objective (cover, problem, under 1 minute), tech (Sprint 1 to-dos with owner and status, architecture, features with owner and status, validation), then the demo, then a closing slide (`end`, listed in `deck.json` under `afterDemo`; the demo fades into it). `--pdf FILE` on `render_slides.cjs` also writes the slides as one PDF with clickable links; the workflow names its outputs `Presentation_Group19_Sprint2.mp4` and `.pdf`.

## Run it locally

```sh
cd threadpilot
export THREADPILOT_DEMO_URL=https://threadpilot-dss5105-track1-i7gxvcy5k7ef5ac9b.webapps.tcloudbase.com
export THREADPILOT_ACCESS_KEY='…'          # the workspace access key; never commit it
node demo/record_demo.cjs --timeline demo/demo_timeline.json --out dist/demo --compress-waits 8
```

Needs Node with Playwright (`npm i -D playwright && npx playwright install chromium`) and, for the two post-processing options, `ffmpeg` on the PATH.

Output in `dist/demo/`:

| File | What it is |
|---|---|
| `demo.webm` | the raw recording of the page, 1920 × 972 |
| `demo.srt` | the captions with the real timestamps of the raw recording |
| `demo_cut.mp4`, `demo_cut.srt` | the same with every "waiting for the model" interval sped up ×N (`--compress-waits N`); a tag on screen says so while it waits |
| `demo_final.mp4` | **the file for the video**: 1920 × 1080, the cut with the captions burned into the band under the page |
| `run_log.json`, `waits.json` | per-step timing, drift, and the wait intervals (for your own editing) |

The access key goes into the tab's storage before the first page loads, so the sign-in dialog never appears in the video. Record on the deployed site after the release branch is deployed: the 23 Oct build does not have the home screen the timeline scrolls through, and the local mock answers no chat questions.

For a phone-shaped recording instead, set `viewport` to `{"width": 430, "height": 932, "scale": 2}`, drop `captions`/`bandHeight` (the caption then floats under the top bar) and add `--pad 1920x1080` to centre it on a 16:9 frame.

## The timeline

`demo_timeline.json` is the script. Each step has `at` (planned seconds) and one action: `say` (caption + subtitle cue), `goto`, `click`, `type`, `press`, `scroll`, `waitAnswer`, `waitFor`, `hold`; `optional: true` lets a step fail without stopping the run. The header in `record_demo.cjs` documents every field. Steps never run earlier than planned; when the model takes longer than the gap you left, every later step shifts by the same amount, so the spacing you planned is kept and the subtitles still line up.

Two steps act for real on the live system: `Confirm send` (sends the chase-up through the connected mailbox to the department address saved in Settings) and `Confirm.` (creates the watch). Both are marked `"real": true`; `--dry-run` (the default in the Actions workflow) leaves them out.

## Editing the final cut

- Keep `demo_cut.mp4` honest: the on-screen tag already says the model waits are sped up; do not cut them out entirely.
- `demo_final.mp4` already has the captions burned in; `demo_cut.srt` is the same text as a subtitle file, if a player or editor needs it.
- Record the voice-over from the teleprompter, not the `say` lines: the captions are too dense to speak. `make_prompter.py`
  turns the spoken lines in `prompter_lines.py` into a silent, scrolling karaoke video timed to a recording's `.srt` (the
  current line filling at about 145 words a minute, the next lines below it with their start times, speaker, clock,
  handover warning); see
  `voice/README.md`. Or let the captions carry the narration and add music.
- A take that goes wrong: fix the step in the timeline and re-run; nothing is cached.

## Full product demo (Video.mp4 in Group19.zip), version of 14 Nov: desk, phone and voice, desk — with the phone's replies as sound

```
python3 demo/make_timeline_demo.py            # writes demo_timeline_demo_a.json (desk 07:00), _b.json (phone, voice), _c.json (desk, rest of the day)
REPLAY_NOW=2026-04-01T07:00:00+08:00 REPLAY_STEP_PACE=0.35 python3 demo/replay_server.py 8765 &
for p in a b c; do node demo/record_demo.cjs --timeline demo/demo_timeline_demo_$p.json --out dist/parts/$p --compress-waits 4 --no-wait-tag; done
python3 demo/assemble_demo.py dist/parts dist/demo --badge "Offline replay · real interface and engine on the factory records · the model's reading of each message is scripted · microphone simulated, replies in a recorded synthetic voice · no real email"
python3 demo/make_demo_script.py --srt dist/demo/ThreadPilot_Demo.srt --duration <seconds> --parts dist/demo/parts.json --out dist/demo/ThreadPilot_Demo_script.txt
python3 demo/make_prompter.py demo --srt dist/demo/ThreadPilot_Demo.srt --duration <seconds> --out dist/demo/ThreadPilot_Demo_prompter.mp4
```

Record the three parts in order on one server run: part A sends the ORD-002 chase-up that the later Activity Log shows.

**Length.** `READ_WPS` in `make_timeline_demo.py` sets how long each caption stays up (2.75 words a second gives about
4:50, so no spoken line needs more than about 135 words a minute). Raise it to shorten the video; the limit is 5:00.

**The phone part (B)** is the real frontend in a 414x720 browser. A recording browser has no microphone or speaker, so
`voice_standin.js` (the timeline's `initScript`) stands in for both. Microphone: it feeds the words of each `speak(...)`
step to the page's speech recognition one by one. Speaker: it logs the exact words `frontend/voice.js` hands to the
speaker (an `@mark` line, saved by the recorder with its time) and shows them in a strip.

**The spoken replies you hear.** `python3 demo/make_voice_audio.py dist/parts/b` renders those words with ffmpeg's
built-in flite voice (offline, plain) into `demo/voice_audio/reply_NN.wav`, and writes each reply's length into
`voice_standin.js` and `voice_audio/index.json`. The timeline then holds each reply for its length, and
`assemble_demo.py` lays each file where the mark says the reply started. The wavs in the repository match the current
answers; if an answer's wording changes, record part B, run `make_voice_audio.py`, regenerate the timeline and record
part B again. The rest of the sound track is silent, for the presenters' voice-over (`ThreadPilot_Demo_prompter.mp4`
marks the three stretches where the phone speaks and the presenter does not).

For a recording with no caveat, screen-record a real phone doing the same steps with the sound on and put it in place
of part B.

## Recording a real alert email on the live site (not the replay)

The replay never delivers email. To film the automatic alert email arriving in a real inbox, use the deployed site:

1. Settings › Mailbox connection: connect Outlook. Settings › Manager delivery preferences: set the recipient and tick
   "Email me at once when something needs a decision today"; save.
2. Open the inbox beside the app and start the screen recording.
3. Settings › Business clock: choose the date (1 April 2026 for the course data). The card works out the moment an
   alert email becomes due from that date and lists what it will contain, for example "2026-04-01 07:00:00, 3 urgent
   items, 1 of them new at that second". Press **Jump to 06:59:58, 2 seconds before, and let it fire**. The clock is
   set two seconds early, the page counts down, and at 07:00:00 it runs the same alert check the server's timer runs.
   The page then says what happened: handed to Outlook, a dry run (switch off), or not sent (no mailbox).
4. Press **Run the check now** (Alert emails card) to show that nothing is sent twice. The clock card now shows the
   next trigger (the next morning with something new), so the demonstration can be repeated.

**Why the trigger is 07:00:00.** Two facts fix it. The urgent rules read whole days: which production days are
complete (a stage below its range three working days running) and how many working days are left to a due date (an
order that will miss even in the best case), so what is urgent changes only when the business date changes. And an
urgent email is sent only between 07:00 and 22:00 (`URGENT_HOURS`): nobody can act on a stalled line at midnight, so
what becomes urgent overnight is held, unrecorded, and the first check from 07:00:00 sends it, alongside the morning
briefing. On the course data, on 1 April ORD-108 (due 3 April) comes within two working days and joins assembly's
sixth day below range and ORD-029; all three go in one email at 07:00:00. Before 14 Nov an urgent email passed at any
hour, which on whole-day rules meant 00:00:00. `alert_policy.next_trigger` computes the moment; a test checks that
00:00, 03:00, 06:59:59, 22:00 and 23:59:59 send nothing and hold the items, and that 07:00:00 to 21:59:59 send them.

Why it sends even after weeks of running: only emails that were really delivered, at or before the current business
time, count as "already emailed" (`alert_policy.relevant_history`).
