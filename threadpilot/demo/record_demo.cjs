#!/usr/bin/env node
/*
 Scripted demo recorder: drives the ThreadPilot site through a fixed timeline (demo_timeline.json), draws a visible
 cursor that glides to every target, a ripple on every click, and a caption bar for the narration; records the whole
 run as a video and writes the captions as an .srt with the real timestamps.

   node demo/record_demo.cjs --timeline demo/demo_timeline.json --out dist/demo
   node demo/record_demo.cjs --timeline demo/demo_timeline.json --out dist/demo --compress-waits 8

 Environment (never put these in the timeline file):
   THREADPILOT_DEMO_URL        the site, e.g. https://threadpilot-…webapps.tcloudbase.com   (or http://127.0.0.1:8765)
   THREADPILOT_ACCESS_KEY      the workspace access key; it is placed in the tab's sessionStorage before the first
                               page loads, so the sign-in dialog never appears on screen
   THREADPILOT_API_ORIGIN      the backend origin the site is configured for (default: read from the page's config)

 Timeline file: {"viewport": {"width": 430, "height": 932, "scale": 2}, "captionTop": 76, "steps": [ … ]}
 (captionTop: px from the top for the caption bar; 0 = along the bottom; default 76 on phone widths, 0 on desktop;
  captionSize: caption font px, default 17 on phones, 26 on desktop;
  captions: "band" + bandHeight: no caption over the page; after recording the frame is extended by bandHeight px at the
  bottom and the .srt is burned into that band — for a 1920x1080 final, record at viewport 1920x972 with bandHeight 108). Each step has "at" (seconds
 on the planned timeline) and one action:
   "say": "text"                   caption shown until the next "say" (or "hide": true); also an .srt cue
   "goto": "#/ai"                  navigate (hash route or full URL)
   "click": "css" | {"text": "…"}  glide the cursor there and click (ripple); {"text"} matches visible text, last match
   "type": {"into": "css", "text": "…", "cps": 14}   click the field, then type at cps characters per second
   "press": "Enter"
   "scroll": {"to": "css"} | {"y": 600} | {"by": 400}   smooth scroll
   "waitAnswer": true              wait until the co-pilot has answered (shows a "waiting for the model" tag; the
                                   interval is listed in waits.json so --compress-waits can speed it up)
   "waitFor": {"css": "…"} | {"text": "…"}            wait for an element (timeout 120 s)
   "hold": 2                       pause that many seconds
   "optional": true                a failing step is logged and skipped instead of stopping the run
 A step runs no earlier than its "at"; if an earlier step overran (the model was slow), every later step shifts by the
 same amount, so the spacing you planned is kept and the .srt still matches the video.
*/
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) => a.startsWith('--') ? [a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true] : []).filter(Boolean));
const timelinePath = path.resolve(args.timeline || path.join(__dirname, 'demo_timeline.json'));
const outDir = path.resolve(args.out || 'dist/demo');
const BASE = (process.env.THREADPILOT_DEMO_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const KEY = process.env.THREADPILOT_ACCESS_KEY || '';
const timeline = JSON.parse(fs.readFileSync(timelinePath, 'utf8'));
if (args['dry-run']) timeline.steps = timeline.steps.filter(s => !s.real);   // steps marked "real": true act on the live system (send, confirm)
const vp = Object.assign({ width: 430, height: 932, scale: 2 }, timeline.viewport || {});
fs.mkdirSync(outDir, { recursive: true });

// ---------------------------------------------------------------- the overlay injected into every page
const OVERLAY = `
(() => {
  if (window.__demo) return;
  const css = \`
    #__demo-cursor{position:fixed;left:0;top:0;width:28px;height:36px;z-index:2147483646;pointer-events:none;
      transform:translate(-4px,-2px);filter:drop-shadow(0 2px 3px rgba(0,0,0,.45));transition:opacity .3s;opacity:0}
    #__demo-cursor.pressed{transform:translate(-4px,-2px) scale(.88)}
    .__demo-ripple{position:fixed;width:16px;height:16px;border-radius:50%;z-index:2147483645;pointer-events:none;
      border:3px solid #E07A5F;background:rgba(224,122,95,.25);transform:translate(-50%,-50%) scale(1);
      animation:__demo-rip .65s ease-out forwards}
    @keyframes __demo-rip{to{transform:translate(-50%,-50%) scale(4.5);opacity:0}}
    #__demo-caption{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:88vw;z-index:2147483644;
      /* on a phone the composer sits at the bottom, so the caption goes under the top bar instead */
      top:var(--demo-caption-top, auto);bottom:var(--demo-caption-bottom, 28px);
      pointer-events:none;background:rgba(20,28,38,.86);color:#F6F4EF;font:600 var(--demo-caption-size, 17px)/1.4 'IBM Plex Sans','Segoe UI',Arial,sans-serif;
      padding:12px 20px;border-radius:12px;text-align:center;letter-spacing:.1px;opacity:0;transition:opacity .25s;
      box-shadow:0 8px 28px rgba(0,0,0,.35)}
    #__demo-caption.on{opacity:1}
    #__demo-wait{position:fixed;right:14px;top:var(--demo-wait-top, 14px);bottom:var(--demo-wait-bottom, auto);z-index:2147483644;pointer-events:none;background:rgba(224,122,95,.95);
      color:#fff;font:600 13px/1 'IBM Plex Sans','Segoe UI',Arial,sans-serif;padding:8px 12px;border-radius:999px;opacity:0;transition:opacity .2s}
    #__demo-wait.on{opacity:1}
  \`;
  const style = document.createElement('style'); style.textContent = css;
  const cursor = document.createElement('div'); cursor.id = '__demo-cursor';
  cursor.innerHTML = '<svg viewBox="0 0 28 36" width="28" height="36"><path d="M3 2 L3 27 L9.5 21.5 L14 32 L18.5 30 L14 19.5 L23 19 Z" fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>';
  const caption = document.createElement('div'); caption.id = '__demo-caption';
  const wait = document.createElement('div'); wait.id = '__demo-wait'; wait.textContent = 'waiting for the model · sped up in the final cut';
  const mount = () => {
    document.documentElement.append(style, cursor, caption, wait);
    const r = document.documentElement.style;
    if (window.__demoCaptionSize) r.setProperty('--demo-caption-size', window.__demoCaptionSize + 'px');
    if (window.__demoCaptionTop === -1) { caption.style.display = 'none'; }
    else if (window.__demoCaptionTop) {
      r.setProperty('--demo-caption-top', window.__demoCaptionTop + 'px'); r.setProperty('--demo-caption-bottom', 'auto');
      r.setProperty('--demo-wait-top', 'auto'); r.setProperty('--demo-wait-bottom', '14px');
    }
  };
  if (document.documentElement) mount(); else document.addEventListener('DOMContentLoaded', mount);
  let pos = { x: window.innerWidth / 2, y: window.innerHeight / 2 }, anim = null;
  const ease = t => t < .5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  window.__demo = {
    pos: () => pos,
    show() { cursor.style.opacity = '1'; cursor.style.left = pos.x + 'px'; cursor.style.top = pos.y + 'px'; },
    moveTo(x, y, ms) {
      return new Promise(res => {
        cursor.style.opacity = '1';
        const from = { ...pos }, t0 = performance.now();
        cancelAnimationFrame(anim);
        const step = now => {
          const k = ease(Math.min(1, (now - t0) / ms));
          pos = { x: from.x + (x - from.x) * k, y: from.y + (y - from.y) * k };
          cursor.style.left = pos.x + 'px'; cursor.style.top = pos.y + 'px';
          if (k < 1) anim = requestAnimationFrame(step); else res();
        };
        anim = requestAnimationFrame(step);
      });
    },
    ripple(x, y) {
      const r = document.createElement('div'); r.className = '__demo-ripple'; r.style.left = x + 'px'; r.style.top = y + 'px';
      document.documentElement.appendChild(r); setTimeout(() => r.remove(), 700);
      cursor.classList.add('pressed'); setTimeout(() => cursor.classList.remove('pressed'), 140);
    },
    caption(text) { if (!text) { caption.classList.remove('on'); return; } caption.textContent = text; caption.classList.add('on'); },
    waiting(on) { wait.classList.toggle('on', !!on); },
  };
})();`;

// ---------------------------------------------------------------- helpers
const sleep = ms => new Promise(r => setTimeout(r, ms));
const now = () => Date.now();
const srtTime = ms => { const h = Math.floor(ms / 3.6e6), m = Math.floor(ms / 6e4) % 60, s = Math.floor(ms / 1e3) % 60, f = Math.floor(ms % 1000); return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(f).padStart(3, '0')}`; };

function locatorFor(page, target) {
  if (typeof target === 'string') return page.locator(target).last();
  if (target.text) return page.getByText(target.text, { exact: !!target.exact }).last();
  if (target.role) return page.getByRole(target.role, { name: target.name }).last();
  throw new Error('bad target ' + JSON.stringify(target));
}

async function glideTo(page, locator, ms = 650, timeout = 8000) {
  await locator.waitFor({ state: 'visible', timeout });
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  await sleep(120);
  const box = await locator.boundingBox();
  if (!box) throw new Error('target not visible');
  const x = box.x + Math.min(box.width - 10, Math.max(10, box.width * 0.4)), y = box.y + box.height / 2;
  await page.evaluate(([x, y, ms]) => window.__demo.moveTo(x, y, ms), [x, y, ms]);
  await page.mouse.move(x, y, { steps: 12 });
  return { x, y };
}

async function clickAt(page, locator, timeout) {
  const { x, y } = await glideTo(page, locator, 650, timeout);
  await page.evaluate(([x, y]) => window.__demo.ripple(x, y), [x, y]);
  await sleep(90);
  await page.mouse.click(x, y);
}

async function chatIdle(page, timeoutMs = 180000) {
  // the composer's button reads "Thinking…" while a request is in flight and the status bubble is on screen:
  // first let the request start (up to 3 s), then wait for it to finish
  await page.waitForFunction(() => /Thinking/.test(document.querySelector('[data-form="chat"] button[type="submit"]')?.textContent || '') || document.querySelector('.bubble[role="status"]'), null, { timeout: 3000, polling: 100 }).catch(() => {});
  await page.waitForFunction(() => {
    const busy = document.querySelector('[data-form="chat"] button[type="submit"]');
    const thinking = [...document.querySelectorAll('.bubble[role="status"]')].length > 0;
    return busy && !busy.disabled && !/Thinking/.test(busy.textContent) && !thinking;
  }, null, { timeout: timeoutMs, polling: 250 });
}

// ---------------------------------------------------------------- main
(async () => {
  // the screencast records at the browser's real scale factor, so the sharpness comes from the launch flag, not emulation
  const browser = await chromium.launch({ args: [`--force-device-scale-factor=${vp.scale}`] });
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    isMobile: vp.width < 700, hasTouch: false,
    recordVideo: { dir: outDir, size: { width: vp.width * vp.scale, height: vp.height * vp.scale } },
  });
  const band = timeline.captions === 'band' ? Number(timeline.bandHeight || 108) : 0;   // captions burned into a band under the page
  const captionTop = band ? -1 : (timeline.captionTop ?? (vp.width < 700 ? 76 : 0));   // px from the top; 0 = bottom; -1 = hidden
  const captionSize = timeline.captionSize ?? (vp.width < 700 ? 17 : 26);
  await context.addInitScript(([t, sz]) => { window.__demoCaptionTop = t; window.__demoCaptionSize = sz; }, [captionTop, captionSize]);
  await context.addInitScript(OVERLAY);
  if (KEY) {
    const origin = process.env.THREADPILOT_API_ORIGIN || '';
    await context.addInitScript(([key, origin]) => {
      try {
        const o = origin || (window.THREADPILOT_API_BASE ? new URL(window.THREADPILOT_API_BASE).origin : null);
        if (o) sessionStorage.setItem('threadpilot-access:' + o, key);
        // config.js runs after this script: keep trying until the base is known
        if (!o) { const t = setInterval(() => { if (window.THREADPILOT_API_BASE) { sessionStorage.setItem('threadpilot-access:' + new URL(window.THREADPILOT_API_BASE).origin, key); clearInterval(t); } }, 20); setTimeout(() => clearInterval(t), 4000); }
      } catch {}
    }, [KEY, origin]);
  }
  const page = await context.newPage();
  page.on('pageerror', e => console.error('page error:', e.message));

  const cues = [], waits = [], log = [];
  const t0 = now();
  let drift = 0, lastCue = null;
  const elapsed = () => now() - t0;
  const closeCue = () => { if (lastCue && lastCue.end == null) lastCue.end = elapsed(); };

  for (const [i, step] of timeline.steps.entries()) {
    const due = step.at * 1000 + drift;
    if (elapsed() < due) await sleep(due - elapsed());
    const started = elapsed();
    try {
      if (step.say !== undefined) {
        closeCue();
        if (step.say) { lastCue = { start: started, end: null, text: step.say }; cues.push(lastCue); }
        await page.evaluate(t => window.__demo.caption(t), step.say || '');
      }
      if (step.hide) { closeCue(); await page.evaluate(() => window.__demo.caption('')); }
      if (step.goto) {
        const onSite = page.url().startsWith(BASE) && step.goto.startsWith('#');
        if (onSite) { await page.evaluate(h => { location.hash = h; }, step.goto); await sleep(600); }   // in-app route change, no reload
        else { const url = step.goto.startsWith('http') ? step.goto : BASE + '/' + step.goto.replace(/^\//, ''); await page.goto(url, { waitUntil: 'load' }); await sleep(900); }
        await page.evaluate(() => window.__demo.show());
      }
      const targetTimeout = step.timeout || (step.optional ? 4000 : 15000);
      if (step.click) await clickAt(page, locatorFor(page, step.click), targetTimeout);
      if (step.type) {
        const field = locatorFor(page, step.type.into);
        await clickAt(page, field, targetTimeout);
        await page.keyboard.type(step.type.text, { delay: Math.round(1000 / (step.type.cps || 14)) });
      }
      if (step.press) await page.keyboard.press(step.press);
      if (step.scroll) {
        if (step.scroll.to) await locatorFor(page, step.scroll.to).evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
        else await page.evaluate(s => window.scrollBy({ top: s.by || 0, left: 0, behavior: 'smooth' }) || (s.y !== undefined && window.scrollTo({ top: s.y, behavior: 'smooth' })), step.scroll);
        await sleep(700);
      }
      if (step.waitFor) {
        const loc = step.waitFor.css ? page.locator(step.waitFor.css).last() : page.getByText(step.waitFor.text).last();
        await loc.waitFor({ state: 'visible', timeout: step.waitFor.timeout || 120000 });
      }
      if (step.waitAnswer) {
        await page.evaluate(() => window.__demo.waiting(true));
        const w = { start: elapsed(), end: null };
        await sleep(600);
        await chatIdle(page, step.timeout || 180000);
        w.end = elapsed(); waits.push(w);
        await page.evaluate(() => window.__demo.waiting(false));
        // bring the newest answer into view
        if (await page.locator('.bubble').count()) await page.locator('.bubble').last().evaluate(el => el.scrollIntoView({ behavior: 'smooth', block: 'start' })).catch(() => {});
        await sleep(400);
      }
      if (step.hold) await sleep(step.hold * 1000);
      log.push({ step: i, at: step.at, started: started / 1000, took: (elapsed() - started) / 1000, ok: true });
    } catch (e) {
      log.push({ step: i, at: step.at, started: started / 1000, error: e.message, skipped: !!step.optional });
      console.error(`step ${i} (${JSON.stringify(step).slice(0, 80)}): ${e.message}`);
      if (!step.optional) { await page.screenshot({ path: path.join(outDir, `failed-step-${i}.png`) }); break; }
    }
    // keep the planned spacing after a slow step: later steps shift by the overrun
    const next = timeline.steps[i + 1];
    if (next) { const plannedNext = next.at * 1000 + drift; if (elapsed() > plannedNext) drift += elapsed() - plannedNext; }
  }
  closeCue();
  await sleep(1200);
  const total = elapsed();
  const video = page.video();
  await context.close();
  const raw = await video.path();
  const webm = path.join(outDir, 'demo.webm');
  fs.renameSync(raw, webm);
  await browser.close();

  // ---------------------------------------------------------------- captions and the run log
  const srt = cues.map((c, i) => `${i + 1}\n${srtTime(c.start)} --> ${srtTime(c.end ?? total)}\n${c.text}\n`).join('\n');
  fs.writeFileSync(path.join(outDir, 'demo.srt'), srt);
  fs.writeFileSync(path.join(outDir, 'waits.json'), JSON.stringify({ total_ms: total, waits }, null, 2));
  fs.writeFileSync(path.join(outDir, 'run_log.json'), JSON.stringify({ base: BASE, viewport: vp, total_s: total / 1000, drift_s: drift / 1000, steps: log }, null, 2));
  console.log(`recorded ${(total / 1000).toFixed(1)} s → ${webm}; ${cues.length} captions → demo.srt; model waits ${waits.length} (${(waits.reduce((a, w) => a + (w.end - w.start), 0) / 1000).toFixed(1)} s)`);

  // ---------------------------------------------------------------- optional ffmpeg post-processing
  const factor = Number(args['compress-waits'] || 0);
  const pad = typeof args.pad === 'string' ? args.pad : null;
  if (factor > 1 || pad || band) {
    if (!which('ffmpeg')) { console.error('ffmpeg not found: skipping --compress-waits / --pad'); return; }
    let input = webm, srtForBurn = path.join(outDir, 'demo.srt');
    if (factor > 1 && waits.length) {
      // split into kept and sped-up segments, re-time the captions the same way
      const segs = []; let cursorMs = 0;
      for (const w of waits) { if (w.start > cursorMs) segs.push([cursorMs, w.start, 1]); segs.push([w.start, w.end, factor]); cursorMs = w.end; }
      if (cursorMs < total) segs.push([cursorMs, total, 1]);
      const filt = segs.map(([s, e, f], i) => `[0:v]trim=start=${(s / 1000).toFixed(3)}:end=${(e / 1000).toFixed(3)},setpts=(PTS-STARTPTS)/${f}[v${i}]`).join(';') + ';' + segs.map((_, i) => `[v${i}]`).join('') + `concat=n=${segs.length}:v=1:a=0[out]`;
      const cut = path.join(outDir, 'demo_cut.mp4');
      execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-threads', '2', '-i', webm, '-filter_complex', filt, '-map', '[out]', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', cut], { stdio: 'inherit' });
      const remap = ms => { let out = 0; for (const [s, e, f] of segs) { if (ms <= s) break; out += (Math.min(ms, e) - s) / f; } return out; };
      const srt2 = cues.map((c, i) => `${i + 1}\n${srtTime(remap(c.start))} --> ${srtTime(remap(c.end ?? total))}\n${c.text}\n`).join('\n');
      fs.writeFileSync(path.join(outDir, 'demo_cut.srt'), srt2);
      const newLen = segs.reduce((a, [s, e, f]) => a + (e - s) / f, 0);
      console.log(`compressed waits ×${factor} → ${cut} (${(newLen / 1000).toFixed(1)} s) + demo_cut.srt`);
      input = cut; srtForBurn = path.join(outDir, 'demo_cut.srt');
    }
    if (band) {
      // the page was recorded band px shorter than the frame: add the band below it and burn the captions into it
      const W = vp.width * vp.scale, H = vp.height * vp.scale + band;
      const out = path.join(outDir, 'demo_final.mp4');
      // libass sizes an .srt on a 288-line canvas, so px values are scaled by 288/H
      const k = 288 / H, fontPx = Math.round(band * 0.32);
      const style = `FontName=DejaVu Sans,FontSize=${Math.max(6, Math.round(fontPx * k))},Bold=1,PrimaryColour=&H00F6F4EF,BorderStyle=1,Outline=0,Shadow=0,Alignment=2,MarginV=${Math.round((band - fontPx) / 2 * k)},MarginL=${Math.round(120 * 384 / W)},MarginR=${Math.round(120 * 384 / W)}`;
      const srtArg = srtForBurn.replace(/\\/g, '/').replace(/:/g, '\\:').replace(/'/g, "\\'");
      execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-threads', '2', '-i', input, '-vf', `pad=${W}:${H}:0:0:color=#1C2733,subtitles='${srtArg}':force_style='${style}'`, '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', out], { stdio: 'inherit' });
      console.log(`captions burned into a ${band}px band → ${out} (${W}x${H})`);
      input = out;
    }
    if (pad) {
      const [W, H] = pad.split('x').map(Number);
      const out = path.join(outDir, `demo_${W}x${H}.mp4`);
      execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-threads', '2', '-i', input, '-vf', `scale=-2:${H}:flags=bicubic,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=#1C2733`, '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '21', out], { stdio: 'inherit' });
      console.log(`padded to ${W}x${H} → ${out}`);
    }
  }
})().catch(e => { console.error(e); process.exit(1); });

function which(bin) { try { execFileSync('which', [bin], { stdio: 'ignore' }); return true; } catch { return false; } }
