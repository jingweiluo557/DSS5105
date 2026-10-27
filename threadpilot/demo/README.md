# Scripted demo recording

`record_demo.cjs` drives the site through `demo_timeline.json` on a fixed timeline, draws a visible cursor that glides to every target with a ripple on each click, shows the narration as a caption bar, records the run as a video and writes the captions as an `.srt` with the real timestamps. It is the 2-minute demo of the Sprint 2 video ("one general manager's day, on a phone").

## Run it

```sh
cd threadpilot
export THREADPILOT_DEMO_URL=https://threadpilot-dss5105-track1-i7gxvcy5k7ef5ac9b.webapps.tcloudbase.com
export THREADPILOT_ACCESS_KEY='…'          # the workspace access key; never commit it
node demo/record_demo.cjs --timeline demo/demo_timeline.json --out dist/demo --compress-waits 8 --pad 1920x1080
```

Needs Node with Playwright (`npm i -D playwright && npx playwright install chromium`) and, for the two post-processing options, `ffmpeg` on the PATH.

Output in `dist/demo/`:

| File | What it is |
|---|---|
| `demo.webm` | the raw recording, phone size at 2× (860 × 1864) |
| `demo.srt` | the captions with the real timestamps of the raw recording |
| `demo_cut.mp4`, `demo_cut.srt` | the same with every "waiting for the model" interval sped up ×N (`--compress-waits N`); a tag on screen says so while it waits |
| `demo_1920x1080.mp4` | the cut, centred on a dark 16:9 frame (`--pad 1920x1080`), ready to drop after the slides |
| `run_log.json`, `waits.json` | per-step timing, drift, and the wait intervals (for your own editing) |

The access key goes into the tab's storage before the first page loads, so the sign-in dialog never appears in the video. Record on the deployed site after the release branch is deployed: the 23 Oct build does not have the home screen the timeline scrolls through, and the local mock answers no chat questions.

## The timeline

`demo_timeline.json` is the script. Each step has `at` (planned seconds) and one action: `say` (caption + subtitle cue), `goto`, `click`, `type`, `press`, `scroll`, `waitAnswer`, `waitFor`, `hold`; `optional: true` lets a step fail without stopping the run. The header in `record_demo.cjs` documents every field. Steps never run earlier than planned; when the model takes longer than the gap you left, every later step shifts by the same amount, so the spacing you planned is kept and the subtitles still line up.

Two steps act for real on the live system: `Confirm send` (sends the chase-up through the connected mailbox to the department address saved in Settings) and `Confirm.` (creates the watch). Both are `optional`; remove them, or type `Cancel` instead, for a dry run.

## Editing the final cut

- Keep `demo_cut.mp4` honest: the on-screen tag already says the model waits are sped up; do not cut them out entirely.
- Use `demo_cut.srt` for subtitles in the editor or on YouTube; the captions are also burned into the video, so turn one of them off.
- Record the voice-over from the `say` lines, or let the captions carry the narration and add music.
- A take that goes wrong: fix the step in the timeline and re-run; nothing is cached.
