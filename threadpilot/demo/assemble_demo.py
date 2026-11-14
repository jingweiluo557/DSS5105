"""Join the three recordings of the product demo into one 1920x1080 video with the captions burned into a band.

  python3 demo/assemble_demo.py <parts dir> <out dir> [--badge "text"] [--spoken-subs] [--phone-live [--phone-guide]] [--email-phone]

<parts dir>/a, /b, /c each hold demo_cut.mp4 and demo_cut.srt from record_demo.cjs (timelines demo_timeline_demo_{a,b,c}.json,
recorded with --compress-waits 4 --no-wait-tag and captions hidden). Parts a and c are the desk (1920x972). Part b is the
phone (414x720 at 2x): it is scaled into a phone frame in the middle of the same canvas, with a short label on each side.
Writes ThreadPilot_Demo.mp4, ThreadPilot_Demo.srt and parts.json (where each part starts and where each spoken reply
plays). The sound track holds only the phone's spoken replies (demo/voice_audio); the rest is silent for the voice-over.
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
    # --phone-live: the phone chapter will be a screen recording of a real phone. The side wording says so, and so that
    # the wording is never shown over the simulated recording, the phone screen is left as a marked empty frame with no
    # synthetic voice: the team's recording (with its own sound) is laid into that frame. parts.json gives the rectangle.
    phone_live = '--phone-live' in sys.argv
    # --phone-guide (with --phone-live): keep the simulated phone recording and its synthetic voice in the frame as a guide
    # to record against and to cover, with a ribbon across the top of the phone screen saying it is guide footage. The
    # team's recording, laid over the same rectangle, covers the ribbon too.
    phone_guide = phone_live and '--phone-guide' in sys.argv
    # --email-phone: while the alert check fires (the caption that starts "06:59:58"), the desk recording moves to the
    # left and a phone-shaped frame is reserved on the right for a recording of the real email arriving on the manager's
    # phone. The frame is empty and marked; parts.json gives its rectangle and times.
    email_phone = '--email-phone' in sys.argv
    email_slot = None
    live_badge = 'Recorded live on a real phone · real microphone and speaker · no email is sent in this chapter'
    work = out / 'work'; work.mkdir(exist_ok=True)
    files, all_cues, starts, offset = [], [], {}, 0.0
    for name in ('a', 'b', 'c'):
        src, dst = parts / name / 'demo_cut.mp4', work / f'{name}.mp4'
        if name == 'b':
            sw, sh = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(src)], capture_output=True, text=True).stdout.strip().split(','))
            ph = 930; pw = round(ph * sw / sh / 2) * 2     # the phone screen on the canvas, as tall as the frame allows
            x, y = (W - pw) // 2, (H - ph) // 2
            left = work / 'left.txt'; left.write_text('On the factory floor\nA real phone, by voice' if phone_live else 'On the factory floor\nA phone, by voice')
            right = work / 'right.txt'; right.write_text('Voice in  ·  spoken reply\nSame rules as at the desk')
            note = work / 'note.txt'; note.write_text('Recorded live on a real phone.\nReal microphone, real speaker:\nthe voice you hear is the phone\'s own.' if phone_live else
                                                      'Real app in a phone-sized browser.\nThe microphone is simulated; the replies\nyou hear are a recorded synthetic voice\nsaying the words the app speaks.')
            hole = work / 'hole.txt'; hole.write_text('YOUR PHONE\nRECORDING\nGOES HERE')
            phone_rect = {'x': x, 'y': y, 'w': pw, 'h': ph}
            side = (f"drawtext=textfile='{left}':font='{FONT}\\:style=Bold':fontsize=44:fontcolor=#1C2733:line_spacing=14:x={x - 14 - 80}-text_w:y=300,"
                    f"drawtext=textfile='{note}':font='{FONT}':fontsize=24:fontcolor=#5B6875:line_spacing=10:x={x - 14 - 80}-text_w:y=470,"
                    f"drawtext=textfile='{right}':font='{FONT}\\:style=Bold':fontsize=36:fontcolor=#1C2733:line_spacing=14:x={x + pw + 14 + 80}:y=320[v]")
            enc = ['-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', dst]
            ribbon = work / 'ribbon.txt'; ribbon.write_text('GUIDE FOOTAGE · replace with the live recording')
            if phone_guide:
                vf = (f"color=c=#E8ECEF:s={W}x{H}:r=30[bg];[0:v]scale={pw}:{ph}:flags=lanczos,fps=30,drawbox=x=0:y=0:w={pw}:h=44:color=#B4532A@0.92:t=fill,"
                      f"drawtext=textfile='{ribbon}':font='{FONT}\\:style=Bold':fontsize=19:fontcolor=white:x=({pw}-text_w)/2:y=12[ph];"
                      f"[bg]drawbox=x={x - 14}:y={y - 14}:w={pw + 28}:h={ph + 28}:color=#111820:t=fill[bz];[bz][ph]overlay={x}:{y}:shortest=1," + side)
                run('-i', src, '-filter_complex', vf, *enc)
            elif phone_live:      # an empty, clearly marked screen instead of the simulated recording
                vf = (f"color=c=#E8ECEF:s={W}x{H}:r=30,drawbox=x={x - 14}:y={y - 14}:w={pw + 28}:h={ph + 28}:color=#111820:t=fill,drawbox=x={x}:y={y}:w={pw}:h={ph}:color=#2A3440:t=fill,"
                      f"drawtext=textfile='{hole}':font='{FONT}\\:style=Bold':fontsize=40:fontcolor=#9AA7B4:line_spacing=18:x={x}+({pw}-text_w)/2:y={y}+({ph}-text_h)/2," + side)
                run('-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-filter_complex', vf, '-t', f'{dur(src):.3f}', *enc)
            else:
                vf = (f"color=c=#E8ECEF:s={W}x{H}:r=30[bg];[0:v]scale={pw}:{ph}:flags=lanczos,fps=30[ph];"
                      f"[bg]drawbox=x={x - 14}:y={y - 14}:w={pw + 28}:h={ph + 28}:color=#111820:t=fill[bz];[bz][ph]overlay={x}:{y}:shortest=1," + side)
                run('-i', src, '-filter_complex', vf, *enc)
        elif name == 'a' and email_phone and any(t.startswith('06:59:58') for _, _, t in cues(parts / name / 'demo_cut.srt')):
            t0, t1 = next((a, b) for a, b, t in cues(parts / name / 'demo_cut.srt') if t.startswith('06:59:58'))
            eh = 820; ew = 470; ex = W - ew - 62; ey = (H - eh) // 2 + 16          # the phone screen on the right
            dw = ex - 14 - 40 - 40; dh = round(dw * H / W / 2) * 2; dx = 40; dy = (H - dh) // 2 + 16   # the desk recording, smaller, on the left
            t_desk = work / 'slot_desk.txt'; t_desk.write_text('On the laptop: the 07:00:00 check fires')
            t_phone = work / 'slot_phone.txt'; t_phone.write_text('On her phone: the email arrives')
            t_hole = work / 'slot_hole.txt'; t_hole.write_text('YOUR PHONE\nRECORDING\nGOES HERE\n\nthe alert email\narriving in\nthe inbox')
            vf = (f"[0:v]scale={W}:{H}:flags=lanczos,fps=30,split[full][s];[s]scale={dw}:{dh}:flags=lanczos[small];"
                  f"color=c=#E8ECEF:s={W}x{H}:r=30,drawbox=x={dx - 2}:y={dy - 2}:w={dw + 4}:h={dh + 4}:color=#C9D1D8:t=fill,"
                  f"drawbox=x={ex - 14}:y={ey - 14}:w={ew + 28}:h={eh + 28}:color=#111820:t=fill,drawbox=x={ex}:y={ey}:w={ew}:h={eh}:color=#2A3440:t=fill,"
                  f"drawtext=textfile='{t_hole}':font='{FONT}\\:style=Bold':fontsize=34:fontcolor=#9AA7B4:line_spacing=16:x={ex}+({ew}-text_w)/2:y={ey}+({eh}-text_h)/2,"
                  f"drawtext=textfile='{t_desk}':font='{FONT}\\:style=Bold':fontsize=30:fontcolor=#1C2733:x={dx}:y={dy - 52},"
                  f"drawtext=textfile='{t_phone}':font='{FONT}\\:style=Bold':fontsize=26:fontcolor=#1C2733:x={ex}+({ew}-text_w)/2:y={ey - 14 - 44}[bg];"
                  f"[bg][small]overlay={dx}:{dy}:shortest=1[alt];[full][alt]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})'[v]")
            run('-i', src, '-filter_complex', vf, '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', dst)
            email_slot = {'from_s': round(t0, 2), 'to_s': round(t1, 2), 'x': ex, 'y': ey, 'w': ew, 'h': eh}
        else:
            run('-i', src, '-vf', f'scale={W}:{H}:flags=lanczos,fps=30', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', dst)
        d = dur(dst); starts[name] = round(offset, 3)
        for a, b, text in cues(parts / name / 'demo_cut.srt'):
            all_cues.append([a + offset, min(b, d) + offset, text])
        files.append(dst); offset += d
    if '--spoken-subs' in sys.argv:
        # The subtitle is the line the presenter says (demo/prompter_lines.py), so the voice-over can be read off the
        # screen. A question the manager speaks into the phone follows in quotes; the AI agent's replies keep their own
        # word-for-word subtitles. The recording's captions set the timing only.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import prompter_lines as pl
        assert len(all_cues) == max(last for _, last, _, _ in pl.DEMO) + 1, 'prompter_lines.DEMO does not match the recording: ' + str(len(all_cues))
        for first, last, who, text in pl.DEMO:
            if who != pl.P:
                all_cues[first][2] = text + (f' “{pl.LIVE[first]}”' if first in pl.LIVE else '')
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
        draw = lambda f, when: f",drawtext=textfile='{esc(f)}':font='{FONT}':fontsize={round(foot * 0.72)}:fontcolor=0x9AA7B4:x=(w-text_w)/2:y=h-{foot}-2{when}"
        if phone_live:      # the line under the captions is true of each chapter: replay at the desk, live on the phone
            lf = work / 'badge_live.txt'; lf.write_text(live_badge)
            b0, b1 = starts['b'], starts['c']
            vf += draw(bf, f":enable='not(between(t,{b0},{b1}))'") + draw(lf, f":enable='between(t,{b0},{b1})'")
        else:
            vf += draw(bf, '')
    final = out / ('ThreadPilot_Demo_phone_guide.mp4' if phone_guide else 'ThreadPilot_Demo_phone_frame.mp4' if phone_live else 'ThreadPilot_Demo.mp4')
    # Sound: the phone's spoken replies (demo/voice_audio, from make_voice_audio.py), each laid where the phone part's
    # marks say the reply started. Everything else is silence, left for the presenters' voice-over.
    audio_dir, marks_file, voice = Path(__file__).resolve().parent / 'voice_audio', parts / 'b' / 'marks_cut.json', []
    if (audio_dir / 'index.json').exists() and marks_file.exists() and (phone_guide or not phone_live):      # a real phone brings its own voice
        by_text = {r['text']: r for r in json.loads((audio_dir / 'index.json').read_text())}
        for m in json.loads(marks_file.read_text()):
            r = by_text.get(json.loads(m['text']).get('speak')) if m['text'].startswith('{') else None
            if r:
                voice.append({'at_s': round(starts['b'] + m['t_s'], 2), 'seconds': r['seconds'], 'file': str(audio_dir / r['file']), 'text': r['text']})
    inputs, graph = ['-i', joined, '-f', 'lavfi', '-t', f'{offset:.3f}', '-i', 'anullsrc=r=48000:cl=stereo'], f'[0:v]{vf}[v];'
    for n, v in enumerate(voice):
        inputs += ['-i', v['file']]
        graph += f"[{n + 2}:a]adelay={round(v['at_s'] * 1000)}:all=1[a{n}];"
    graph += '[1:a]' + ''.join(f'[a{n}]' for n in range(len(voice))) + f'amix=inputs={len(voice) + 1}:duration=first:normalize=0[a]'
    run(*inputs, '-filter_complex', graph, '-map', '[v]', '-map', '[a]', '-r', '30', '-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k', '-t', f'{offset:.3f}', '-movflags', '+faststart', final)
    (out / 'parts.json').write_text(json.dumps({'starts': starts, 'total_s': round(offset, 2), 'phone_screen_in_1920x1080': phone_rect, 'email_phone_slot_in_1920x1080': email_slot, 'voice': [{k: v[k] for k in ('at_s', 'seconds', 'text')} for v in voice]}, indent=1))
    print(f'{len(voice)} spoken replies laid in: ' + ', '.join(f"{v['at_s']:.1f}-{v['at_s'] + v['seconds']:.1f} s" for v in voice))
    print(f'{final} · {offset:.1f} s ({int(offset // 60)}:{int(offset % 60):02d}) · {len(all_cues)} captions · parts start at {starts}')


if __name__ == '__main__':
    main()
