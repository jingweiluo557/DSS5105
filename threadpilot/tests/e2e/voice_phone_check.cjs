#!/usr/bin/env node
/* Voice in, voice out and phone layout, checked in a phone-sized browser with stand-ins for the microphone and the
   speaker (a headless browser has neither). Run against the offline replay server:

     python demo/replay_server.py 8765 &      node tests/e2e/voice_phone_check.cjs [http://127.0.0.1:8765]

   Checks: (1) browser speech recognition → the spoken order number is cleaned up, the question is sent, the answer is
   read aloud; (2) no browser recognition → a clip is recorded and sent to /api/v1/voice/transcribe, same result;
   (3) the server has no speech key → a plain message, nothing sent; (4) "send now" by voice is never submitted;
   (5) the speaker button turns spoken replies on for typed questions, and "Read aloud" starts and stops;
   (6) at 390 px no page scrolls sideways, form controls are 16 px, and the floating "Ask AI" does not cover content. */
const { chromium, devices } = require('playwright');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const fails = [];
const check = (ok, what) => { console.log((ok ? 'ok   ' : 'FAIL ') + what); if (!ok) fails.push(what); };

async function page(browser, mode, transcribeStatus) {
  const p = await (await browser.newContext({ ...devices['iPhone 13'] })).newPage();
  await p.addInitScript(mode => {
    window.__spoken = [];
    const synth = { speaking: false, cancel() { this.speaking = false; }, speak(u) { if (u.text.trim()) { this.speaking = true; window.__spoken.push(u.text); } setTimeout(() => { this.speaking = false; u.onend && u.onend(); }, 120); }, getVoices: () => [] };
    Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
    window.SpeechSynthesisUtterance = function (t) { this.text = t; };
    if (mode === 'webspeech') {
      window.SpeechRecognition = window.webkitSpeechRecognition = function () { this.start = () => setTimeout(() => { this.onresult({ results: [[{ transcript: window.__say }]] }); this.onend(); }, 200); this.stop = () => this.onend(); };
    } else {
      delete window.SpeechRecognition; delete window.webkitSpeechRecognition;
      Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) }, configurable: true });
      window.MediaRecorder = function () { this.state = 'inactive'; this.start = () => { this.state = 'recording'; }; this.stop = () => { this.state = 'inactive'; this.ondataavailable({ data: new Blob(['x'], { type: 'audio/webm' }) }); this.onstop(); }; };
      window.MediaRecorder.isTypeSupported = t => t === 'audio/webm';
    }
  }, mode);
  if (mode === 'record') await p.route('**/api/v1/voice/transcribe', r => r.fulfill(transcribeStatus === 503
    ? { status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'VOICE_UNAVAILABLE', message: 'Voice transcription needs the model key on the server. Type the question instead.' } }) }
    : { status: 200, contentType: 'application/json', body: JSON.stringify({ text: 'where is ord 5', normalized: 'where is ORD-005' }) }));
  await p.goto(BASE + '/#/ai'); await p.waitForSelector('[data-action="voice"][data-voice-ready]', { timeout: 20000 });
  return p;
}
const bubbles = p => p.evaluate(() => [...document.querySelectorAll('.bubble')].map(b => b.textContent.trim()));
const mic = p => p.locator('[data-action="voice"]').first();

(async () => {
  const browser = await chromium.launch();
  let p = await page(browser, 'webspeech');
  await p.evaluate(() => { window.__say = 'where is o r d zero zero five'; });
  await mic(p).click(); await p.waitForTimeout(7000);
  let b = await bubbles(p);
  check(b[0] === 'where is ORD-005', '1 spoken order number is cleaned up and the question is sent');
  check((b[1] || '').includes('ORD-005'), '1 the question is answered');
  check((await p.evaluate(() => window.__spoken.join(' '))).includes('order 0 0 5'), '1 the answer is read aloud, order number digit by digit');
  await p.evaluate(() => { window.__say = 'send now'; });
  await mic(p).click(); await p.waitForTimeout(1500);
  check((await bubbles(p)).length === b.length && await p.locator('textarea[name="visible-question"]').first().inputValue() === 'send now', '4 "send now" by voice waits in the box for a tap');
  await p.locator('textarea[name="visible-question"]').first().fill('');
  await p.locator('[data-action="voice-replies"]').first().click();
  check(await p.locator('[data-action="voice-replies"]').first().getAttribute('aria-pressed') === 'true', '5 the speaker button turns spoken replies on');
  await p.evaluate(() => { window.__spoken = []; });
  await p.locator('textarea[name="visible-question"]').first().fill('where is ORD-029'); await p.locator('form.composer button[type=submit]').first().click(); await p.waitForTimeout(7000);
  check((await p.evaluate(() => window.__spoken.join(' '))).includes('order 0 2 9'), '5 a typed question is answered aloud while spoken replies are on');
  const read = p.locator('[data-action="read-aloud"]').last();
  await p.evaluate(() => { window.speechSynthesis.speak = function (u) { this.speaking = true; window.__spoken.push(u.text); }; });   // from here an utterance lasts until stopped
  await read.click(); const during = await read.textContent(); await read.click();
  check(/Stop/.test(during) && /Read aloud/.test(await read.textContent()), '5 "Read aloud" starts and stops');

  p = await page(browser, 'record');
  await mic(p).click(); await p.waitForTimeout(300); await mic(p).click(); await p.waitForTimeout(7000);
  b = await bubbles(p);
  check(b[0] === 'where is ORD-005' && (b[1] || '').includes('ORD-005'), '2 without browser recognition a recorded clip is transcribed by the server and answered');
  p = await page(browser, 'record', 503);
  await mic(p).click(); await p.waitForTimeout(300); await mic(p).click(); await p.waitForTimeout(1200);
  check((await p.evaluate(() => document.querySelector('#toast').textContent)).includes('Type the question instead') && (await bubbles(p)).length === 0, '3 no speech key on the server: a plain message, nothing sent');

  for (const route of ['#/', '#/ai', '#/orders', '#/risk', '#/exceptions', '#/messages', '#/predictions', '#/feasibility', '#/activity', '#/settings', '#/order?id=ORD-029']) {
    await p.goto(BASE + '/' + route); await p.waitForTimeout(1500);
    const m = await p.evaluate(() => ({
      wide: document.documentElement.scrollWidth > innerWidth + 1,
      small: [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]),select,textarea')].filter(e => e.getBoundingClientRect().width && parseFloat(getComputedStyle(e).fontSize) < 16).length,
      floating: [...document.querySelectorAll('.floating')].filter(e => e.getBoundingClientRect().width).length }));
    check(!m.wide && !m.small && !m.floating, `6 ${route} fits a 390 px phone (sideways scroll ${m.wide}, controls under 16 px ${m.small}, floating button ${m.floating})`);
  }
  await browser.close();
  console.log(fails.length ? `\n${fails.length} check(s) failed` : '\nall checks passed');
  process.exit(fails.length ? 1 : 0);
})();
