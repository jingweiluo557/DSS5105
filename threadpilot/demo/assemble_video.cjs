#!/usr/bin/env node
/*
 Builds the presentation video: the rendered slides, each held for the seconds in its speaker notes, then the
 recorded demo, into one 1920x1080 mp4, with the narration (slide notes + demo captions) as one .srt.

   node demo/assemble_video.cjs --slides dist/slides --demo dist/demo --out dist/presentation [--burn] [--no-demo]

   --burn      also burn the slide narration into a caption band at the bottom of each slide (default: slides are
               clean and the narration is spoken; the .srt is there for YouTube or the editor)
   --no-demo   slides only
   --fade N    cross-fade seconds between slides (default 0.5)

 Inputs: <slides>/slides.json from render_slides.cjs; <demo>/demo_final.mp4 (+ demo_cut.srt) from record_demo.cjs.
 Outputs: <out>/presentation.mp4, presentation.srt, slides.mp4, slides.srt. Warns when the total passes 4:55.
*/
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const args = Object.fromEntries(process.argv.slice(2).map((a, i, all) => a.startsWith('--') ? [a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true] : []).filter(Boolean));
const slidesDir = path.resolve(args.slides || 'dist/slides');
const demoDir = path.resolve(args.demo || 'dist/demo');
const outDir = path.resolve(args.out || 'dist/presentation');
const fade = Number(args.fade ?? 0.5);
const burn = !!args.burn;
const withDemo = !args['no-demo'];
fs.mkdirSync(outDir, { recursive: true });

const meta = JSON.parse(fs.readFileSync(path.join(slidesDir, 'slides.json'), 'utf8'));
const W = meta.width, H = meta.height;
const srtTime = s => { const ms = Math.round(s * 1000); const h = Math.floor(ms / 3.6e6), m = Math.floor(ms / 6e4) % 60, sec = Math.floor(ms / 1e3) % 60, f = ms % 1000; return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')},${String(f).padStart(3, '0')}`; };
const run = a => execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-threads', '2', ...a], { stdio: 'inherit' });

// ---------------------------------------------------------------- slides → slides.mp4 (one input per slide, cross-faded)
const inputs = [], filters = [];
meta.slides.forEach((s, i) => { inputs.push('-loop', '1', '-t', String(s.seconds + (i < meta.slides.length - 1 ? fade : 0)), '-i', s.file); filters.push(`[${i}:v]scale=${W}:${H},format=yuv420p,fps=30,setsar=1[s${i}]`); });
let chain = '[s0]', t = 0;
for (let i = 1; i < meta.slides.length; i++) {
  t += meta.slides[i - 1].seconds;
  const label = i === meta.slides.length - 1 ? '[slides]' : `[x${i}]`;
  filters.push(`${chain}[s${i}]xfade=transition=fade:duration=${fade}:offset=${t}${label}`);
  chain = label;
}
if (meta.slides.length === 1) filters.push('[s0]copy[slides]');
const slidesMp4 = path.join(outDir, 'slides.mp4');
run([...inputs, '-filter_complex', filters.join(';'), '-map', '[slides]', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', slidesMp4]);

// the narration for the slides, one cue per slide (split long notes into readable 2-line cues)
let cursor = 0; const cues = [];
for (const s of meta.slides) {
  const text = (s.narration || '').replace(/^[“"]|[”"]$/g, '').trim();
  const sentences = text ? text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g).map(x => x.trim()).filter(Boolean) : [];
  const chars = sentences.reduce((a, x) => a + x.length, 0) || 1;
  let at = cursor;
  sentences.forEach((sent, i) => {
    const d = i === sentences.length - 1 ? cursor + s.seconds - at : s.seconds * (sent.length / chars);
    cues.push({ start: at, end: at + d, text: sent }); at += d;
  });
  cursor += s.seconds;
}
const slidesLen = cursor;
const slidesSrt = cues.map((c, i) => `${i + 1}\n${srtTime(c.start)} --> ${srtTime(c.end)}\n${c.text}\n`).join('\n');
fs.writeFileSync(path.join(outDir, 'slides.srt'), slidesSrt);

let slidesPart = slidesMp4;
if (burn) {
  const k = 288 / H, fontPx = 34;
  const style = `FontName=DejaVu Sans,FontSize=${Math.round(fontPx * k)},Bold=1,PrimaryColour=&H00F6F4EF,BackColour=&H66000000,BorderStyle=4,Outline=0,Shadow=0,Alignment=2,MarginV=${Math.round(28 * k)},MarginL=${Math.round(160 * 384 / W)},MarginR=${Math.round(160 * 384 / W)}`;
  slidesPart = path.join(outDir, 'slides_captioned.mp4');
  run(['-i', slidesMp4, '-vf', `subtitles='${path.join(outDir, 'slides.srt').replace(/:/g, '\\:')}':force_style='${style}'`, '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', slidesPart]);
}

// ---------------------------------------------------------------- + demo → presentation.mp4
let total = slidesLen;
const parts = [slidesPart];
if (withDemo) {
  const demo = ['demo_final.mp4', 'demo_cut.mp4', 'demo.webm'].map(f => path.join(demoDir, f)).find(fs.existsSync);
  if (!demo) { console.error(`no demo recording in ${demoDir}; run record_demo.cjs first or pass --no-demo`); process.exit(1); }
  const probe = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height:format=duration', '-of', 'csv=p=0', demo]).toString().trim().split(/\s+/);
  const demoLen = Number(probe.pop().split(',').pop());
  const [dw, dh] = probe[0].split(',').map(Number);
  let demoPart = demo;
  if (dw !== W || dh !== H || !demo.endsWith('.mp4')) {
    demoPart = path.join(outDir, 'demo_fit.mp4');
    run(['-i', demo, '-vf', `scale=-2:${H}:flags=bicubic,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=#1C2733,fps=30,setsar=1`, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', demoPart]);
  }
  parts.push(demoPart);
  const demoSrt = ['demo_cut.srt', 'demo.srt'].map(f => path.join(demoDir, f)).find(fs.existsSync);
  if (demoSrt) {
    const shift = s => { const [h, m, rest] = s.split(':'); const [sec, ms] = rest.split(','); return srtTime(Number(h) * 3600 + Number(m) * 60 + Number(sec) + Number(ms) / 1000 + slidesLen); };
    const shifted = fs.readFileSync(demoSrt, 'utf8').replace(/(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})/g, (_, a, b) => `${shift(a)} --> ${shift(b)}`);
    const renumbered = (slidesSrt.trim() + '\n\n' + shifted.trim()).split(/\n\n+/).map((blk, i) => blk.replace(/^\d+\n/, `${i + 1}\n`)).join('\n\n') + '\n';
    fs.writeFileSync(path.join(outDir, 'presentation.srt'), renumbered);
  }
  total += demoLen;
}
const list = path.join(outDir, 'parts.txt');
fs.writeFileSync(list, parts.map(p => `file '${p.replace(/'/g, "'\\''")}'`).join('\n') + '\n');
const final = path.join(outDir, 'presentation.mp4');
run(['-f', 'concat', '-safe', '0', '-i', list, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', '-r', '30', final]);
const mm = Math.floor(total / 60), ss = Math.round(total % 60);
console.log(`presentation.mp4: slides ${Math.round(slidesLen)} s${withDemo ? ` + demo ${Math.round(total - slidesLen)} s` : ''} = ${mm}:${String(ss).padStart(2, '0')} → ${final}`);
if (total > 295) console.warn(`::warning title=length::the video is ${mm}:${String(ss).padStart(2, '0')}, over the 5:00 limit: shorten slide timings in the notes or the demo timeline`);
