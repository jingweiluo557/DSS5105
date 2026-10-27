#!/usr/bin/env node
/*
 Renders the Sprint 2 deck (demo/slides: the same files as the Claude Slides artifact) to 1920x1080 PNGs and writes
 slides.json with each slide's duration and narration, read from the speaker notes ("0:08–0:30 · [Presenter 1]. …").

   node demo/render_slides.cjs --slides demo/slides --out dist/slides

 If demo/slides/deck.pdf exists (export the deck from the Slides page: Share → Export → PDF), its pages are used
 instead of the HTML, so edits made on the Slides page need no HTML edit here; the notes still come from the HTML.
*/
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) => a.startsWith('--') ? [a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true] : []).filter(Boolean));
const slidesDir = path.resolve(args.slides || path.join(__dirname, 'slides'));
const outDir = path.resolve(args.out || 'dist/slides');
const W = 1920, H = 1080;
fs.mkdirSync(outDir, { recursive: true });

const deck = JSON.parse(fs.readFileSync(path.join(slidesDir, 'deck.json'), 'utf8'));
const fontLinks = Object.values(deck.faces || {}).map(f => f.href).filter(Boolean).map(h => `<link rel="stylesheet" href="${h}">`).join('\n');

// the defaults the Slides runtime applies (format.md): sizes, weights, line-heights, ruled table cells
const BASE_CSS = `
*{margin:0;box-sizing:border-box} html,body{width:${W}px;height:${H}px;overflow:hidden;background:#000}
section{position:relative;width:${W}px;height:${H}px;overflow:hidden;display:flex;flex-direction:column}
h1{font-size:96px;font-weight:600;line-height:1.1} h2{font-size:64px;font-weight:600;line-height:1.15} h3{font-size:44px;font-weight:600;line-height:1.2}
p{font-size:32px;font-weight:400;line-height:1.4} ul,ol{font-size:32px;line-height:1.4;padding-left:1.2em}
div{display:flex;flex-direction:column} div[style*="display:flex"]{flex-direction:row} div[style*="display:grid"]{display:grid}
table{border-collapse:collapse;width:100%;line-height:1.35} td,th{border:1px solid rgba(0,0,0,.14);padding:.35em .6em;text-align:left;vertical-align:top} th{font-weight:600}
tr[style*="background"] th{background:transparent}
img{display:block} a{color:inherit}
x-connector{display:block;align-self:center;height:0;border-top:4px solid currentColor;position:relative;flex:none}
x-connector::after{content:"";position:absolute;right:-2px;top:-9px;border:7px solid transparent;border-left:11px solid currentColor}
aside{display:none}
`;

function parseNotes(html) {
  const m = html.match(/<aside>([\s\S]*?)<\/aside>/);
  if (!m) return { seconds: null, narration: '' };
  const raw = m[1].replace(/\s+/g, ' ').trim();
  const t = raw.match(/^(\d+):(\d\d)\s*[–-]\s*(\d+):(\d\d)\s*·?\s*(?:\[[^\]]*\]\.?\s*)?/);
  const seconds = t ? (Number(t[3]) * 60 + Number(t[4])) - (Number(t[1]) * 60 + Number(t[2])) : null;
  let narration = t ? raw.slice(t[0].length) : raw;
  narration = narration.split(/\s(?:Before recording|Cut straight)/)[0].trim();   // the production reminders are not narration
  return { seconds, narration };
}

(async () => {
  const order = deck.order;
  const pdf = path.join(slidesDir, 'deck.pdf');
  const slides = [];
  if (fs.existsSync(pdf)) {
    execFileSync('pdftoppm', ['-png', '-r', '144', '-scale-to-x', String(W), '-scale-to-y', String(H), pdf, path.join(outDir, 'page')]);
    const pages = fs.readdirSync(outDir).filter(f => /^page-?\d+\.png$/.test(f)).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    if (pages.length !== order.length) console.warn(`deck.pdf has ${pages.length} pages, deck.json lists ${order.length} slides: notes are matched by position`);
    pages.forEach((f, i) => { const id = order[i] || `page${i + 1}`; const file = path.join(outDir, `${String(i + 1).padStart(2, '0')}-${id}.png`); fs.renameSync(path.join(outDir, f), file); slides.push({ id, file }); });
  } else {
    const browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: W, height: H } });
    for (const [i, id] of order.entries()) {
      const html = fs.readFileSync(path.join(slidesDir, 'slides', `${id}.html`), 'utf8');
      // images are inlined: a page set with setContent has no origin, so file:// pictures would not load
      const section = html.match(/<section[\s\S]*<\/section>/)[0].replace(/src="\.\.\/assets\/([^"]+)"/g, (_, f) => {
        const file = path.join(slidesDir, 'assets', f); const ext = path.extname(f).slice(1).replace('jpg', 'jpeg');
        return `src="data:image/${ext};base64,${fs.readFileSync(file).toString('base64')}"`;
      });
      await page.setContent(`<!doctype html><html><head><meta charset="utf-8">${fontLinks}<style>${BASE_CSS}</style></head><body>${section}</body></html>`, { waitUntil: 'load' });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(300);
      const file = path.join(outDir, `${String(i + 1).padStart(2, '0')}-${id}.png`);
      await page.screenshot({ path: file, clip: { x: 0, y: 0, width: W, height: H } });
      slides.push({ id, file });
    }
    await browser.close();
  }
  for (const s of slides) {
    const html = fs.existsSync(path.join(slidesDir, 'slides', `${s.id}.html`)) ? fs.readFileSync(path.join(slidesDir, 'slides', `${s.id}.html`), 'utf8') : '';
    Object.assign(s, parseNotes(html));
  }
  const missing = slides.filter(s => !s.seconds);
  if (missing.length) { const each = Math.max(8, Math.round(170 / slides.length)); missing.forEach(s => { s.seconds = each; }); console.warn(`no timing in the notes of ${missing.map(s => s.id).join(', ')}: ${each} s each`); }
  fs.writeFileSync(path.join(outDir, 'slides.json'), JSON.stringify({ width: W, height: H, slides }, null, 2));
  const total = slides.reduce((a, s) => a + s.seconds, 0);
  console.log(`${slides.length} slides → ${outDir} (${total} s planned)`);
})().catch(e => { console.error(e); process.exit(1); });
