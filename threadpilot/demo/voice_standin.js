/* Stand-ins for the microphone and the speaker, for the demo recording only (record_demo.cjs "initScript").
   A headless browser has neither, so the recording could not otherwise show voice at all. The product code is untouched:
   the real frontend/voice.js drives these exactly as it drives a phone's speech recognition and speech synthesis.
     microphone: SpeechRecognition delivers the words in window.__voiceSay one by one, as a phone does while you speak;
     speaker:    speechSynthesis takes as long as the words would take to say, and, because the video is silent, shows
                 the words it is "speaking" in a strip at the top of the page (labelled as such).
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

  let queue = [], timer = null, strip = null;
  const show = text => {
    if (!strip) {
      strip = document.createElement('div');
      strip.style.cssText = 'position:fixed;left:8px;right:8px;top:76px;z-index:2147483000;background:#1C2733;color:#F6F4EF;border-radius:14px;padding:10px 14px;font:600 14px/1.45 system-ui,sans-serif;box-shadow:0 8px 24px #0005;pointer-events:none;transition:opacity .2s';
      document.documentElement.appendChild(strip);
    }
    strip.style.opacity = text ? '1' : '0';
    if (text) strip.innerHTML = '<span style="color:#F2B880">🔊 Spoken reply</span> <span style="opacity:.6;font-weight:500">(sound, shown as text in this silent recording)</span><br>' + text.replace(/</g, '&lt;');
  };
  const next = () => {
    const u = queue.shift();
    if (!u) { synth.speaking = false; show(''); return; }
    synth.speaking = true;
    if (u.text.trim() && u.volume !== 0) show(u.text);
    timer = setTimeout(() => { u.onend && u.onend(); next(); }, u.volume === 0 || !u.text.trim() ? 10 : Math.max(900, u.text.split(/\s+/).length / WORDS_PER_S * 1000));
  };
  const synth = { speaking: false, pending: false, paused: false, getVoices: () => [], resume() {}, pause() {}, addEventListener() {},
    speak(u) { queue.push(u); if (!synth.speaking) next(); },
    cancel() { queue = []; clearTimeout(timer); synth.speaking = false; show(''); } };
  Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true });
  window.SpeechSynthesisUtterance = function (text) { this.text = text; this.volume = 1; };
})();
