"""Karaoke teleprompter videos: the words to SAY, timed to a recorded video, with no slides or footage.

    python3 demo/make_prompter.py demo  --srt ThreadPilot_Demo.srt      --duration 249.5 --out ThreadPilot_Demo_prompter.mp4
    python3 demo/make_prompter.py presentation --srt Presentation_Group19.srt --duration 289.2 --out Presentation_Group19_prompter.mp4

Play the prompter next to (or instead of) the video while recording the voice-over. For each spoken line in
demo/prompter_lines.py the whole chunk is shown at once and the words fill in at a speakable pace (about 145 words a
minute, faster only when the window is tight), so the presenter can see both what comes next and whether they are
ahead or behind. On screen as well: who speaks, a clock (m:ss / total), the caption the viewer sees at that moment,
a bar for the time left on this line, the next line, and a handover warning three seconds before the speaker changes.

Optional: --script FILE writes the spoken lines with their start times as plain text. Needs ffmpeg with libass.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompter_lines  # noqa: E402

W, H = 1920, 1080
NATURAL_WPS = 2.4          # the karaoke fill pace when the window allows it (about 145 words a minute)
MAX_WPS = 2.75             # warn above this: hard to say clearly
COLOURS = {prompter_lines.W: '&H00B48CFF', prompter_lines.M: '&H00FFB45A', prompter_lines.K: '&H0078DC8C'}   # BGR
SHORT = {prompter_lines.W: 'Wendy', prompter_lines.M: 'Matthew', prompter_lines.K: 'Kevin'}


def srt(path: Path) -> list[dict]:
    out = []
    for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8').strip()):
        rows = block.strip().splitlines()
        m = re.match(r'(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)', rows[1])
        g = [int(x) for x in m.groups()]
        out.append({'start': g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, 'end': g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000,
                    'text': ' '.join(rows[2:]).strip()})
    return out


def words(text: str) -> list[str]:
    return text.split()


def plan(lines, cues, duration):
    """Each spoken line gets the window from its first cue's start to the next line's start (or the end)."""
    chunks = []
    for i, (a, b, who, text) in enumerate(lines):
        start = cues[a]['start']
        end = cues[lines[i + 1][0]]['start'] if i + 1 < len(lines) else duration
        n = len(words(text))
        speak = min(max(n / NATURAL_WPS, 0.5), (end - start) * 0.94)
        chunks.append(dict(start=start, end=end, who=who, text=text, cues=(a, b), n=n, speak=speak, wps=n / (end - start)))
    return chunks


def ts(sec: float) -> str:
    cs = int(round(sec * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def clock(sec: float) -> str:
    s = int(sec)
    return f'{s // 60}:{s % 60:02d}'


def esc(text: str) -> str:
    return text.replace('\\', '\\\\').replace('{', '(').replace('}', ')')


def karaoke(text: str, speak: float) -> str:
    """{\\kf} per word, weighted by length (a rough syllable count), summing to the speaking time."""
    ws = words(text)
    weight = [max(2, len(re.sub(r'[^\w]', '', w))) + 3 for w in ws]      # + 3: every word costs a beat, plus its length
    total = sum(weight)
    out, used = [], 0
    for i, (w, k) in enumerate(zip(ws, weight)):
        cs = round(speak * 100 * k / total) if i < len(ws) - 1 else max(1, round(speak * 100) - used)
        used += cs
        out.append(f'{{\\kf{cs}}}{esc(w)} ')
    return ''.join(out).rstrip()


def size_for(n: int) -> int:
    return 84 if n <= 14 else 74 if n <= 24 else 62 if n <= 45 else 52 if n <= 70 else 46


def ass(chunks, cues, duration, title) -> str:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Say,Inter,72,&H00FFFFFF,&H00786A5E,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,170,170,0,1
Style: Who,Inter,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,90,90,56,1
Style: Clock,Inter,46,&H00E6E0DA,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,9,90,90,56,1
Style: Ctx,Inter,28,&H00A09080,&H00FFFFFF,&H00000000,&H00000000,0,-1,0,0,100,100,0,0,1,0,0,8,240,240,156,1
Style: Next,Inter,34,&H00968676,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,1,90,90,70,1
Style: Hand,Inter,40,&H0040A0FF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,3,90,90,70,1
Style: Bar,Inter,10,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Tag,Inter,24,&H00786A5E,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,90,90,14,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    add = lambda s, e, style, text, layer=1: ev.append(f'Dialogue: {layer},{ts(s)},{ts(e)},{style},,0,0,0,,{text}')
    total = clock(duration)
    for s in range(int(duration) + 1):                                    # the running clock
        add(s, min(s + 1, duration), 'Clock', f'{clock(s)} / {total}')
    add(0, duration, 'Tag', esc(title) + ' · teleprompter (silent): say the bright words as they fill')
    # overall progress, full width at the very bottom
    add(0, duration, 'Bar', f'{{\\pos(0,{H - 8})\\1c&H00403830&\\p1}}m 0 0 l {W} 0 {W} 8 0 8', 0)
    add(0, duration, 'Bar', f'{{\\pos(0,{H - 8})\\1c&H00A0A0A0&\\clip(0,{H - 8},0,{H})\\t(0,{int(duration * 1000)},\\clip(0,{H - 8},{W},{H}))\\p1}}m 0 0 l {W} 0 {W} 8 0 8', 1)
    for c in cues:                                                        # what the viewer sees at that moment
        add(c['start'], c['end'], 'Ctx', 'On screen:  ' + esc(c['text']))
    for i, ch in enumerate(chunks):
        s, e, col = ch['start'], ch['end'], COLOURS[ch['who']]
        add(s, e, 'Who', f'{{\\1c{col}}}{SHORT[ch["who"]]}{{\\1c&H00968676&\\b0\\fs32}}   {esc(ch["who"].split(" (")[0])}')
        add(s, e, 'Say', f'{{\\fs{size_for(ch["n"])}\\1c&H00FFFFFF&}}' + karaoke(ch['text'], ch['speak']))
        # time left on this line: a bar under the header that empties
        dur = int((e - s) * 1000)
        add(s, e, 'Bar', f'{{\\pos(90,124)\\1c{col}\\clip(90,124,{W - 90},132)\\t(0,{dur},\\clip(90,124,90,132))\\p1}}m 0 0 l {W - 180} 0 {W - 180} 8 0 8')
        if i + 1 < len(chunks):
            nx = chunks[i + 1]
            preview = ' '.join(words(nx['text'])[:14]) + (' …' if nx['n'] > 14 else '')
            add(s, e, 'Next', f'Next{" (" + SHORT[nx["who"]] + ")" if nx["who"] != ch["who"] else ""}:  {esc(preview)}')
            if nx['who'] != ch['who']:
                add(max(s, e - 3), e, 'Hand', f'{{\\1c{COLOURS[nx["who"]]}}}Handover to {SHORT[nx["who"]]} ▸')
        else:
            add(s, e, 'Next', 'Last line.')
    return head + '\n'.join(ev) + '\n'


def script_text(chunks, title, duration) -> str:
    out = [title.upper(), f'Spoken narration for the voice-over, timed to the video ({clock(duration)}).',
           'The burned-in captions are for reading; these shorter lines are for speaking, at about 145 words a minute.',
           'The teleprompter video shows the same lines, filling in at speaking pace.', '=' * 72, '']
    who = None
    for ch in chunks:
        if ch['who'] != who:
            who = ch['who']
            out += ['', f'--- {who} ---', '']
        out.append(f'[{clock(ch["start"])}-{clock(ch["end"])}]  {ch["text"]}')
    totals = {}
    for ch in chunks:
        totals[ch['who']] = totals.get(ch['who'], 0) + ch['end'] - ch['start']
    out += ['', 'Voice time: ' + ' · '.join(f'{SHORT[k]} {round(v)} s' for k, v in totals.items()), '']
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('which', choices=['demo', 'presentation'])
    ap.add_argument('--srt', required=True, type=Path)
    ap.add_argument('--duration', type=float, required=True)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--script', type=Path)
    ap.add_argument('--check', action='store_true', help='only report the pace of each line')
    a = ap.parse_args()
    lines = prompter_lines.DEMO if a.which == 'demo' else prompter_lines.PRESENTATION
    title = 'ThreadPilot · product demo' if a.which == 'demo' else 'ThreadPilot · Sprint 3 presentation'
    cues = srt(a.srt)
    assert lines[-1][1] == len(cues) - 1 and all(lines[i + 1][0] == lines[i][1] + 1 for i in range(len(lines) - 1)), \
        'prompter lines must cover every cue once, in order'
    chunks = plan(lines, cues, a.duration)
    fast = [c for c in chunks if c['wps'] > MAX_WPS]
    for c in chunks:
        flag = '  <-- too fast' if c in fast else ''
        print(f"{clock(c['start'])}-{clock(c['end'])} {c['end'] - c['start']:5.1f}s {c['n']:3d}w {c['wps'] * 60:4.0f} wpm  {SHORT[c['who']]:7s} {c['text'][:60]}{flag}")
    print(f'{len(chunks)} lines; fastest {max(c["wps"] for c in chunks) * 60:.0f} wpm; {len(fast)} over {MAX_WPS * 60:.0f} wpm')
    if a.script:
        a.script.write_text(script_text(chunks, title, a.duration), encoding='utf-8')
    if a.check or not a.out:
        return
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / 'prompter.ass'
        sub.write_text(ass(chunks, cues, a.duration, title), encoding='utf-8')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=0x141C26:s={W}x{H}:r=30:d={a.duration}',
                        '-vf', f'ass={sub}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', str(a.out)], check=True)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
