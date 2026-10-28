#!/usr/bin/env node
/*
 Builds the presentation video: the rendered slides, each held for the seconds in its speaker notes, then the
 recorded demo, into one 1920x1080 mp4, with the narration (slide notes + demo captions) as one .srt.

   node demo/assemble_video.cjs --slides dist/slides --demo dist/demo --out dist/presentation [--burn] [--no-demo]

   --burn      also burn the slide narration into a caption band at the bottom of each slide (default: slides are
               clean and the narration is spoken; the .srt is there for YouTube or the editor)
   --no-demo   slides only
   --fade N    cross-fade seconds between slides (default 0.5)

   --voice DIR voice-over clips (default demo/voice): one clip per slide named after the slide id (cover.m4a,
               problem.m4a, … .m4a/.mp3/.wav/.aac/.ogg) — each slide then lasts as long as its clip plus a short pause,
               instead of the time in its notes; or one clip slides.* laid over all the slides at the notes' timing;
               and demo.* laid over the demo. Slides without a clip keep their notes' timing, silent.

 Slides listed in deck.json "afterDemo" (marked after: true in slides.json) close the video after the demo, with a fade.
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
const voiceDir = path.resolve(args.voice || path.join(__dirname, 'voice'));
const AUDIO_EXT = ['.m4a', '.mp3', '.wav', '.aac', '.ogg'];
const clipFor = name => AUDIO_EXT.map(e => path.join(voiceDir, name + e)).find(fs.existsSync) || null;
const audioLen = f => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString().trim());
const PAUSE = 0.7;   // seconds of silence after a slide's clip before the next slide
let perSlideVoice = false;
for (const s of meta.slides) {
  s.clip = clipFor(s.id);
  if (s.clip) { s.seconds = Math.ceil((audioLen(s.clip) + PAUSE) * 10) / 10; perSlideVoice = true; }
}
const closing = meta.slides.filter(s => s.after);          // shown after the demo
meta.slides = meta.slides.filter(s => !s.after);
const slidesVoice = !perSlideVoice ? clipFor('slides') : null;
const demoVoice = clipFor('demo');
if (perSlideVoice) console.log(`voice-over: ${meta.slides.filter(s => s.clip).length} of ${meta.slides.length} slides have a clip; those slides last as long as their clip`);
else if (slidesVoice) console.log(`voice-over: ${path.basename(slidesVoice)} over the slides`);
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
const slidesVideo = path.join(outDir, 'slides_video.mp4');
run([...inputs, '-filter_complex', filters.join(';'), '-map', '[slides]', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', slidesVideo]);
// the slides' audio track: each slide's clip padded with silence to the slide's length (or silence), joined in order
{
  const ain = [], af = [];
  meta.slides.forEach((s, i) => {
    if (s.clip) { ain.push('-i', s.clip); af.push(`[${ain.length / 2}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur=${s.seconds},atrim=0:${s.seconds},asetpts=PTS-STARTPTS[a${i}]`); }
    else af.push(`anullsrc=r=48000:cl=stereo,atrim=0:${s.seconds},asetpts=PTS-STARTPTS[a${i}]`);
  });
  if (slidesVoice) { ain.push('-i', slidesVoice); af.length = 0; af.push(`[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur=${meta.slides.reduce((a, s) => a + s.seconds, 0)}[voice]`); }
  const mix = slidesVoice ? '[voice]' : meta.slides.map((_, i) => `[a${i}]`).join('') + `concat=n=${meta.slides.length}:v=0:a=1[voice]`;
  const graph = slidesVoice ? af.join(';') : af.join(';') + ';' + mix;
  run(['-i', slidesVideo, ...ain, '-filter_complex', graph, '-map', '0:v', '-map', '[voice]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', slidesMp4]);
}

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
  run(['-i', slidesMp4, '-vf', `subtitles='${path.join(outDir, 'slides.srt').replace(/:/g, '\\:')}':force_style='${style}'`, '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', '-c:a', 'copy', slidesPart]);
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
  const demoPart = path.join(outDir, 'demo_fit.mp4');
  const vf = ((dw !== W || dh !== H) ? `scale=-2:${H}:flags=bicubic,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=#1C2733,fps=30,setsar=1` : 'fps=30,setsar=1')
    + (closing.length ? `,fade=t=out:st=${Math.max(0, demoLen - 0.6).toFixed(2)}:d=0.6` : '');   // fade into the closing slide
  if (demoVoice) run(['-i', demo, '-i', demoVoice, '-filter_complex', `[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur=${demoLen}[va]`, '-map', '0:v', '-map', '[va]', '-vf', vf, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', '-c:a', 'aac', '-b:a', '160k', '-shortest', demoPart]);
  else run(['-i', demo, '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-map', '0:v', '-map', '1:a', '-vf', vf, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', '-c:a', 'aac', '-b:a', '96k', '-shortest', demoPart]);
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
// ---------------------------------------------------------------- + closing slides (fade in from the demo's fade-out)
let srtOut = fs.existsSync(path.join(outDir, 'presentation.srt')) && withDemo ? fs.readFileSync(path.join(outDir, 'presentation.srt'), 'utf8').trim() : slidesSrt.trim();
for (const [i, s] of closing.entries()) {
  const part = path.join(outDir, `closing_${i + 1}.mp4`);
  const vf = `scale=${W}:${H},format=yuv420p,fps=30,setsar=1,fade=t=in:st=0:d=0.6`;
  const audio = s.clip ? ['-i', s.clip] : ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo'];
  run(['-loop', '1', '-t', String(s.seconds), '-i', s.file, ...audio, '-filter_complex', `[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur=${s.seconds},atrim=0:${s.seconds}[a]`,
       '-map', '0:v', '-map', '[a]', '-vf', vf, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', '-c:a', 'aac', '-b:a', '160k', '-t', String(s.seconds), part]);
  parts.push(part);
  const text = (s.narration || '').trim();
  if (text) { const n = srtOut ? srtOut.split(/\n\n+/).length : 0; srtOut += `\n\n${n + 1}\n${srtTime(total)} --> ${srtTime(total + s.seconds)}\n${text}`; }
  total += s.seconds;
}
fs.writeFileSync(path.join(outDir, 'presentation.srt'), srtOut.trim() + '\n');
const list = path.join(outDir, 'parts.txt');
fs.writeFileSync(list, parts.map(p => `file '${p.replace(/'/g, "'\\''")}'`).join('\n') + '\n');
const final = path.join(outDir, 'presentation.mp4');
run(['-f', 'concat', '-safe', '0', '-i', list, '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-crf', '20', '-r', '30', '-c:a', 'aac', '-b:a', '160k', final]);
const mm = Math.floor(total / 60), ss = Math.round(total % 60);
const closingLen = closing.reduce((a, s) => a + s.seconds, 0);
console.log(`presentation.mp4: slides ${Math.round(slidesLen)} s${withDemo ? ` + demo ${Math.round(total - slidesLen - closingLen)} s` : ''}${closingLen ? ` + closing ${Math.round(closingLen)} s` : ''} = ${mm}:${String(ss).padStart(2, '0')} → ${final}`);
if (total > 295) console.warn(`::warning title=length::the video is ${mm}:${String(ss).padStart(2, '0')}, over the 5:00 limit: shorten slide timings in the notes or the demo timeline`);
