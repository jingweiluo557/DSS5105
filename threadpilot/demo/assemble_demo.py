"""Join the three recordings of the product demo into one 1920x1080 video with the captions burned into a band.

  python3 demo/assemble_demo.py <parts dir> <out dir> [--badge "text"]

<parts dir>/a, /b, /c each hold demo_cut.mp4 and demo_cut.srt from record_demo.cjs (timelines demo_timeline_demo_{a,b,c}.json,
recorded with --compress-waits 4 --no-wait-tag and captions hidden). Parts a and c are the desk (1920x972). Part b is the
phone (414x720 at 2x): it is scaled into a phone frame in the middle of the same canvas, with a short label on each side.
Writes ThreadPilot_Demo.mp4, ThreadPilot_Demo.srt and parts.json (where each part starts, for the script).
"""
import json, re, subprocess, sys
from pathlib import Path

W, H, BAND = 1920, 972, 108
FONT = 'DejaVu Sans'


def run(*a):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-threads', '2', *map(str, a)], check=True)


def dur(f):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)], capture_output=True, text=True).stdout)


def t2s(t):
    h, m, s = t.replace(',', '.').split(':'); return int(h) * 3600 + int(m) * 60 + float(s)


def s2t(x):
    ms = round(x * 1000); return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'


def cues(f):
    out = []
    for block in re.split(r'\n\s*\n', Path(f).read_text().strip()):
        lines = block.strip().split('\n')
        if len(lines) >= 3 and '-->' in lines[1]:
            a, b = [t2s(x.strip()) for x in lines[1].split('-->')]
            out.append([a, b, ' '.join(lines[2:])])
    return out


def main():
    parts, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    badge = sys.argv[sys.argv.index('--badge') + 1] if '--badge' in sys.argv else ''
    work = out / 'work'; work.mkdir(exist_ok=True)
    files, all_cues, starts, offset = [], [], {}, 0.0
    for name in ('a', 'b', 'c'):
        src, dst = parts / name / 'demo_cut.mp4', work / f'{name}.mp4'
        if name == 'b':
            sw, sh = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(src)], capture_output=True, text=True).stdout.strip().split(','))
            ph = 930; pw = round(ph * sw / sh / 2) * 2     # the phone screen on the canvas, as tall as the frame allows
            x, y = (W - pw) // 2, (H - ph) // 2
            left = work / 'left.txt'; left.write_text('On the factory floor\nA phone, by voice')
            right = work / 'right.txt'; right.write_text('Voice in  ·  spoken reply\nSame rules as at the desk')
            note = work / 'note.txt'; note.write_text('Real app in a phone-sized browser.\nMicrophone and speaker are simulated\nfor this silent recording.')
            vf = (f"color=c=#E8ECEF:s={W}x{H}:r=30[bg];[0:v]scale={pw}:{ph}:flags=lanczos,fps=30[ph];"
                  f"[bg]drawbox=x={x - 14}:y={y - 14}:w={pw + 28}:h={ph + 28}:color=#111820:t=fill[bz];[bz][ph]overlay={x}:{y}:shortest=1,"
                  f"drawtext=textfile='{left}':font='{FONT}\\:style=Bold':fontsize=44:fontcolor=#1C2733:line_spacing=14:x={x - 14 - 80}-text_w:y=300,"
                  f"drawtext=textfile='{note}':font='{FONT}':fontsize=24:fontcolor=#5B6875:line_spacing=10:x={x - 14 - 80}-text_w:y=470,"
                  f"drawtext=textfile='{right}':font='{FONT}\\:style=Bold':fontsize=36:fontcolor=#1C2733:line_spacing=14:x={x + pw + 14 + 80}:y=320[v]")
            run('-i', src, '-filter_complex', vf, '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', dst)
        else:
            run('-i', src, '-vf', f'scale={W}:{H}:flags=lanczos,fps=30', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', dst)
        d = dur(dst); starts[name] = round(offset, 3)
        for a, b, text in cues(parts / name / 'demo_cut.srt'):
            all_cues.append([a + offset, min(b, d) + offset, text])
        files.append(dst); offset += d
    for i in range(len(all_cues) - 1):               # a caption ends where the next begins
        all_cues[i][1] = min(all_cues[i][1], all_cues[i + 1][0])
    srt = out / 'ThreadPilot_Demo.srt'
    srt.write_text('\n'.join(f'{i}\n{s2t(a)} --> {s2t(b)}\n{t}\n' for i, (a, b, t) in enumerate(all_cues, 1)))
    lst = work / 'list.txt'; lst.write_text(''.join(f"file '{f}'\n" for f in files))
    joined = work / 'joined.mp4'; run('-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', joined)
    # the same band, font and badge line as record_demo.cjs draws for a single recording
    FH = H + BAND; foot = round(BAND * 0.2) if badge else 0
    k = 288 / FH; font_px = round((BAND - foot) * (0.34 if badge else 0.32))
    style = (f"FontName={FONT},FontSize={max(6, round(font_px * k))},Bold=1,PrimaryColour=&H00F6F4EF,BorderStyle=1,Outline=0,Shadow=0,Alignment=2,"
             f"MarginV={round((foot + (BAND - foot - font_px * 2.3) / 2) * k)},MarginL=12,MarginR=12")
    esc = lambda p: str(p).replace('\\', '/').replace(':', '\\:').replace("'", "\\'")
    vf = f"pad={W}:{FH}:0:0:color=#1C2733,subtitles='{esc(srt)}':force_style='{style}'"
    if badge:
        bf = work / 'badge.txt'; bf.write_text(badge)
        vf += f",drawtext=textfile='{esc(bf)}':font='{FONT}':fontsize={round(foot * 0.72)}:fontcolor=0x9AA7B4:x=(w-text_w)/2:y=h-{foot}-2"
    final = out / 'ThreadPilot_Demo.mp4'
    run('-i', joined, '-vf', vf, '-r', '30', '-an', '-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', final)
    (out / 'parts.json').write_text(json.dumps({'starts': starts, 'total_s': round(offset, 2)}, indent=1))
    print(f'{final} · {offset:.1f} s ({int(offset // 60)}:{int(offset % 60):02d}) · {len(all_cues)} captions · parts start at {starts}')


if __name__ == '__main__':
    main()
