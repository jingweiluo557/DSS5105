"""Burns subtitles (.srt) into a video that has none: bold white text on a dark box, bottom centre, 1920x1080.

    python3 demo/burn_subs.py presentation_clean.mp4 Presentation_Group19.srt Presentation_Group19.mp4

Used for the Sprint 3 video: the subtitles are the spoken lines (demo/make_prompter.py presentation --subs), so the
voice, the subtitles and the teleprompter say the same words. The input must be built without burned captions:
assemble_video.cjs without --burn, and a demo folder holding only the uncaptioned recording (demo_cut.mp4, padded to
1920x1080 with the caption band left empty) as demo_final.mp4. See demo/voice/README.md, "Subtitles".
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STYLE = ('Style: Sub,DejaVu Sans,36,&H00F6F4EF,&H00F6F4EF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,4,6,0,2,200,200,14,1')


def ass_time(x: str) -> str:
    h, m, s = x.strip().replace(',', '.').split(':')
    cs = round((int(h) * 3600 + int(m) * 60 + float(s)) * 100)
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def main(video: str, srt: str, out: str):
    events = []
    for block in re.split(r'\n\s*\n', Path(srt).read_text(encoding='utf-8').strip()):
        rows = block.splitlines()
        a, b = rows[1].split('-->')
        text = ' '.join(rows[2:]).replace('{', '(').replace('}', ')')
        events.append(f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Sub,,0,0,0,,{text}')
    head = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n'
            '[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, '
            'Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, '
            f'MarginR, MarginV, Encoding\n{STYLE}\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, '
            'MarginV, Effect, Text\n')
    with tempfile.TemporaryDirectory() as tmp:
        sub = Path(tmp) / 'subs.ass'
        sub.write_text(head + '\n'.join(events) + '\n', encoding='utf-8')
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', video, '-vf', f'ass={sub}', '-c:v', 'libx264', '-preset', 'veryfast',
                        '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', out], check=True)
    print(f'{len(events)} subtitles burned -> {out}')


if __name__ == '__main__':
    main(*sys.argv[1:4])
