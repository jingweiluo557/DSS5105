/* Stand-ins for the microphone and the speaker, for the demo recording only (record_demo.cjs "initScript").
   A headless browser has neither, so the recording could not otherwise show voice at all. The product code is untouched:
   the real frontend/voice.js drives these exactly as it drives a phone's speech recognition and speech synthesis.
     microphone: SpeechRecognition delivers the words in window.__voiceSay one by one, as a phone does while you speak;
     speaker:    speechSynthesis takes as long as the recorded audio of that reply (demo/make_voice_audio.py renders each
                 reply with an offline text-to-speech voice; assemble_demo.py lays it under the video at the same moment),
                 and shows the words being spoken in a strip at the top of the page.
   The video's captions and badge say that microphone and speaker are simulated. */
(() => {
  const WORDS_PER_S = 2.8;
  function Recognition() {
    let timer = null, done = false;
    const end = () => { if (done) return; done = true; clearInterval(timer); this.onend && this.onend(); };
    this.start = () => {
      const words = String(window.__voiceSay || '').split(/\s+/).filter(Boolean); let n = 0;
      timer = setInterval(() => {
        n += 1;
        this.onresult && this.onresult({ results: [[{ transcript: words.slice(0, n).join(' ') }]] });
        if (n >= words.length) { clearInterval(timer); setTimeout(end, 450); }
      }, 1000 / WORDS_PER_S);
    };
    this.stop = end;
  }
  window.SpeechRecognition = window.webkitSpeechRecognition = Recognition;

  /* How long each whole reply lasts as recorded audio (seconds), written here by demo/make_voice_audio.py so the strip
     stays up exactly as long as the sound that assemble_demo.py lays over it. A reply not in the table is estimated. */
  const REPLY_SECONDS = /*REPLY_SECONDS*/{"order 0 0 5, TrendCart, 500 Scarf: in progress, stage knitting, due 20 April; last recorded activity 24 March. Due in 19 days. No recorded activity for 8 days.": 11.58, "Northwind Apparel has the most active pieces: 8,000 pieces across 5 active orders.": 4.77, "A draft to washing about order 0 8 3 is ready. Nothing has been sent. Read it, then tap to confirm.": 5.72}/*END*/;
  let queue = [], timer = null, strip = null, batch = null;
  const show = text => {
    if (!strip) {
      strip = document.createElement('div');
      strip.style.cssText = 'position:fixed;left:8px;right:8px;top:76px;z-index:2147483000;background:#1C2733;color:#F6F4EF;border-radius:14px;padding:10px 14px;font:600 14px/1.45 system-ui,sans-serif;box-shadow:0 8px 24px #0005;pointer-events:none;transition:opacity .2s';
      document.documentElement.appendChild(strip);
    }
    strip.style.opacity = text ? '1' : '0';
    if (text) strip.innerHTML = '<span style="color:#F2B880">\uD83D\uDD0A Spoken reply</span> <span style="opacity:.6;font-weight:500">(the words being spoken)</span><br>' + text.replace(/</g, '&lt;');
  };
  const words = t => t.split(/\s+/).filter(Boolean).length;
  const next = () => {
    const u = queue.shift();
    if (!u) { synth.speaking = false; show(''); return; }
    synth.speaking = true;
    const silent = u.volume === 0 || !u.text.trim();
    if (!silent) show(u.text);
    timer = setTimeout(() => { u.onend && u.onend(); next(); }, silent ? 10 : Math.max(700, u.__ms || words(u.text) / WORDS_PER_S * 1000));
  };
  // voice.js queues every sentence of a reply in one go: collect them, look up the reply's recorded length, share it out
  const begin = () => {
    const said = queue.filter(u => u.volume !== 0 && u.text.trim());
    const text = said.map(u => u.text.trim()).join(' ');
    if (text) {
      const total = (REPLY_SECONDS[text] || said.reduce((n, u) => n + words(u.text), 0) / WORDS_PER_S) * 1000, all = said.reduce((n, u) => n + words(u.text), 0);
      said.forEach(u => { u.__ms = total * words(u.text) / all; });
      console.log('@mark ' + JSON.stringify({ speak: text }));
    }
    batch = null; next();
  };
  const synth = { speaking: false, pending: false, paused: false, getVoices: () => [], resume() {}, pause() {}, addEventListener() {},
    speak(u) { queue.push(u); if (!synth.speaking && !batch) batch = setTimeout(begin, 0); },
    cancel() { queue = []; clearTimeout(timer); clearTimeout(batch); batch = null; synth.speaking = false; show(''); } };
  Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
  window.SpeechSynthesisUtterance = function (text) { this.text = text; this.volume = 1; };
})();
