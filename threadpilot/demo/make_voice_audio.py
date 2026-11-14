"""Record the phone's spoken replies for the demo video.

  python3 demo/make_voice_audio.py <dir of a part-B recording>     # reads its marks.json

The replies are exactly what frontend/voice.js hands to the speaker in the recording (voice_standin.js logs each one as an
"@mark" line; record_demo.cjs saves them with their times). Each is rendered offline with ffmpeg's built-in flite voice
(a plain synthetic voice, no network), written to demo/voice_audio/reply_NN.wav, and its length is written into the
table in voice_standin.js so that, on the next recording, the on-screen "speaking" lasts exactly as long as the sound.
So: record part B once, run this, regenerate the timeline (it holds each reply for its length), record part B again.
A phone's own voice will sound better than this one; the words and the timing are what the product produces.
"""
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / 'voice_audio'
VOICE, TEMPO = 'slt', 1.12


def prepare(text: str) -> str:
    """Small helps for the offline voice only (a phone's voice needs none): brand names, the thousands comma."""
    text = re.sub(r'(?<=\d),(?=\d{3}\b)', '', text)
    return text.replace('TrendCart', 'Trend Cart').replace('UrbanThread', 'Urban Thread').replace('&', 'and').replace(';', ',')


def main():
    marks = json.loads((Path(sys.argv[1]) / 'marks.json').read_text())
    texts = [json.loads(m['text'])['speak'] for m in marks if m['text'].startswith('{"speak"')]
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob('reply_*.wav'): old.unlink()
    index = []
    for i, text in enumerate(texts, 1):
        src, wav = OUT / 'say.txt', OUT / f'reply_{i:02d}.wav'
        src.write_text(prepare(text))
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', f"flite=textfile='{src}':voice={VOICE}",
                        '-af', f'atempo={TEMPO},silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,loudnorm=I=-16:TP=-1.5,aresample=24000',
                        '-ac', '1', str(wav)], check=True)
        src.unlink()
        seconds = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(wav)], capture_output=True, text=True).stdout)
        index.append({'file': wav.name, 'seconds': round(seconds, 2), 'text': text})
        print(f'{wav.name}  {seconds:5.1f} s  {len(text.split())} words  {text[:90]}')
    (OUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1))
    js = HERE / 'voice_standin.js'
    table = json.dumps({r['text']: r['seconds'] for r in index}, ensure_ascii=False)
    js.write_text(re.sub(r'/\*REPLY_SECONDS\*/.*?/\*END\*/', lambda _: f'/*REPLY_SECONDS*/{table}/*END*/', js.read_text(), flags=re.S))
    print(f'{len(index)} replies, {sum(r["seconds"] for r in index):.1f} s of speech; table written to voice_standin.js')


if __name__ == '__main__':
    main()
