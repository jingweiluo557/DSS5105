# Scripted demo recording

`record_demo.cjs` drives the site through `demo_timeline.json` on a fixed timeline, draws a visible cursor that glides to every target with a ripple on each click, shows the narration as a caption bar, records the run as a video and writes the captions as an `.srt` with the real timestamps. It is the 2-minute demo of the Sprint 2 video ("one general manager's day"), recorded as a 1920 × 1080 desktop video: the app fills 1920 × 972 and the captions sit in a 108 px band underneath, so nothing covers the page.

## Run it without installing anything: GitHub Actions

Actions tab → **Record the presentation video** → **Run workflow**. A GitHub runner renders the slides (`demo/slides`, each held for the seconds in its speaker notes), records the demo on the deployed site, joins the two and uploads `presentation-video` as an artifact on the run page: `presentation.mp4` (1920 × 1080, slides then demo, under 5 minutes), `presentation.srt` (the whole narration), `slides.mp4`/`slides.srt`, the slide PNGs and `demo_final.mp4`. One-time setup: add the workspace access key as the repository secret `THREADPILOT_ACCESS_KEY` (Settings → Secrets and variables → Actions → New repository secret). The workflow's inputs: the site URL, `dry_run` (on by default: leaves out the send and the watch confirmation), the speed-up factor, the timeline file, `include_demo` (off = slides only, needs no secret) and `burn_slide_captions` (on by default: the narration appears as captions on the slides; turn it off for clean slides under a recorded voice-over).

## The slides

`demo/slides/` holds the deck as files (`deck.json`, one HTML per slide, `assets/`), the same content as the Claude Slides artifact. `render_slides.cjs` turns them into 1920 × 1080 PNGs; `assemble_video.cjs` holds each for the duration in its speaker note (`<aside>0:08–0:30 · [Presenter] …`), cross-fades between them, and appends the demo. To change timing or wording, edit the HTML (the `<aside>` is the narration and the timing). To use a deck edited on the Slides page instead, export it as PDF to `demo/slides/deck.pdf`: the pages are then used in place of the HTML, and the notes still come from the HTML.

Fill the placeholders before the final take: attendance on the cover, the Sprint 1 feedback on slide 2, the live second-pass score on slide 5, the YouTube link on slides 1 and 8.

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
- `demo_final.mp4` already has the captions burned in; upload `demo_cut.srt` to YouTube as well only if you want closed captions people can switch off.
- Record the voice-over from the `say` lines, or let the captions carry the narration and add music.
- A take that goes wrong: fix the step in the timeline and re-run; nothing is cached.
