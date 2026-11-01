/* Voice in / voice out for a manager on the floor.
   Voice in: tap ♩ and speak. The browser's own speech recognition listens when it has one (Chrome, Edge, Safari);
   otherwise the page records a short clip and the server transcribes it (POST /api/v1/voice/transcribe, nothing stored).
   Spoken order numbers are cleaned up ("O R D zero zero five" → ORD-005), and the question is sent as soon as you stop
   speaking. One exception, on purpose: a confirmation ("send now", "confirm", "save it") is never sent by voice. It is
   put in the box and waits for a tap, so a misheard word can never send an email.
   Voice out: an answer to a spoken question is read aloud (its first three lines); every answer has a "Read aloud" button. */
(function(){
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canListen = !!Recognition, canSpeak = 'speechSynthesis' in window;
  const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  const CONFIRM = /^(send now|confirm|confirm send|confirm save|confirm create|confirm update|save it|确认|确认发送|确认保存)[.!。！]?$/i;
  const DIGITS = {zero:'0', oh:'0', o:'0', one:'1', two:'2', to:'2', too:'2', three:'3', four:'4', for:'4', five:'5', six:'6', seven:'7', eight:'8', nine:'9'};
  const ORDER_RE = /\b(?:o\.?\s*r\.?\s*d\.?|ord|or\s+d|order\s+(?:number|no\.?|id))[\s\-#:]*((?:\d|zero|oh|one|two|three|four|five|six|seven|eight|nine)(?:[\s\-]*(?:\d|zero|oh|one|two|three|four|five|six|seven|eight|nine)){0,2})\b/gi;
  // Same rule as the server (api/voice_api.py): a bare "order 500" stays as it is, it may be a quantity.
  function normalizeSpoken(text){
    return String(text || '').replace(ORDER_RE, (whole, spoken) => {
      const digits = (spoken.match(/\d+|[a-z]+/gi) || []).map(t => DIGITS[t.toLowerCase()] ?? t).join('');
      const n = Number(digits);
      return /^\d+$/.test(digits) && n > 0 && n < 1000 ? 'ORD-' + String(n).padStart(3, '0') : whole;
    });
  }
  let voiceAsked = false, recognizer = null, recorder = null;
  const say = msg => { if (typeof toast === 'function') toast(msg); };
  function areaOf(button){ const form = button.closest('form'); return form && form.querySelector('textarea[name="visible-question"]'); }
  function finish(button, text){
    const area = areaOf(button); if (!area) return;
    const clean = normalizeSpoken(text).trim();
    area.value = clean;
    if (!clean) return;
    if (CONFIRM.test(clean)) { area.focus(); say('Heard “' + clean + '”. Tap Send to confirm: voice never confirms an action on its own.'); return; }
    voiceAsked = true;
    const form = area.closest('form');
    if (form && form.requestSubmit) form.requestSubmit(); else form?.querySelector('button[type="submit"]')?.click();
  }
  function setListening(button, on, label){
    button.classList.toggle('listening', on);
    if (on) button.setAttribute('aria-pressed', 'true'); else button.removeAttribute('aria-pressed');
    button.textContent = on ? '■' : '♩';
    const area = areaOf(button);
    if (area) area.placeholder = on ? (label || 'Listening… speak your question') : 'Ask about an order, a risk, or your next move…';
  }
  function listen(button){
    if (recognizer) { recognizer.stop(); return; }
    recognizer = new Recognition();
    recognizer.lang = navigator.language && navigator.language.startsWith('zh') ? navigator.language : 'en-SG';
    recognizer.interimResults = true; recognizer.maxAlternatives = 1;
    let text = '';
    setListening(button, true);
    recognizer.onresult = e => { text = Array.from(e.results).map(r => r[0].transcript).join(' ').trim(); const area = areaOf(button); if (area) area.value = normalizeSpoken(text); };
    recognizer.onerror = e => { text = ''; say(e.error === 'not-allowed' ? 'Microphone access was refused.' : e.error === 'no-speech' ? 'Nothing heard; tap ♩ and try again.' : 'Could not hear that; try again.'); };
    recognizer.onend = () => { recognizer = null; setListening(button, false); finish(button, text); };
    try { recognizer.start(); } catch (err) { recognizer = null; setListening(button, false); }
  }
  async function record(button){
    if (recorder) { recorder.stop(); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({audio: true}); }
    catch { say('Microphone access was refused.'); return; }
    const type = ['audio/webm', 'audio/ogg', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || '';
    recorder = new MediaRecorder(stream, type ? {mimeType: type} : undefined);
    const chunks = [];
    const limit = setTimeout(() => recorder && recorder.state === 'recording' && recorder.stop(), 30000);
    recorder.ondataavailable = e => e.data.size && chunks.push(e.data);
    recorder.onstop = async () => {
      clearTimeout(limit); stream.getTracks().forEach(t => t.stop()); recorder = null;
      setListening(button, false); button.disabled = true;
      const blob = new Blob(chunks, {type: (type || 'audio/webm').split(';')[0]});
      try {
        const r = await window.threadpilotFetch(window.THREADPILOT_API_BASE + '/api/v1/voice/transcribe', {method: 'POST', headers: {'Content-Type': blob.type}, body: blob});
        const data = await r.json();
        if (!r.ok) throw new Error(data.error?.message || data.detail?.message || 'Could not transcribe that.');
        finish(button, data.normalized || data.text || '');
      } catch (err) { say(err.message || 'Could not transcribe that.'); }
      finally { button.disabled = false; }
    };
    recorder.start(); setListening(button, true, 'Recording… tap ■ when you finish');
  }
  function firstLines(text, n = 3){
    return String(text || '').replace(/^\(Reading[^)]*\)\s*/, '').replace(/[*_`#>|]/g, ' ').split(/\n+/).map(l => l.trim()).filter(Boolean).slice(0, n).join('. ');
  }
  function speakText(text){
    if (!canSpeak || !text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(firstLines(text));
    utter.lang = 'en-SG'; utter.rate = 1.0;
    window.speechSynthesis.speak(utter);
  }
  function speak(button){
    if (!canSpeak) return;
    if (window.speechSynthesis.speaking) { window.speechSynthesis.cancel(); return; }
    const bubble = button.closest('.bubble');
    const note = bubble && bubble.querySelector('.note');
    speakText(note ? note.textContent : '');
  }
  // An answer to a spoken question is read aloud when it arrives.
  if (typeof ask === 'function') {
    const textAsk = ask;
    ask = async function(question){
      const spoken = voiceAsked; voiceAsked = false;
      const before = (state.chat || []).length;
      await textAsk(question);
      const answer = (state.chat || []).slice(before).reverse().find(m => m.role === 'assistant');
      if (spoken && answer) speakText(answer.text);
    };
  }
  // Capture phase so this runs before app.js's demo handler for the same button.
  document.addEventListener('click', e => {
    const voice = e.target.closest('[data-action="voice"]');
    if (voice && (canListen || canRecord)) { e.preventDefault(); e.stopImmediatePropagation(); canListen ? listen(voice) : record(voice); return; }
    const read = e.target.closest('[data-action="read-aloud"]');
    if (read) { e.preventDefault(); e.stopImmediatePropagation(); speak(read); }
  }, true);
  // Add a "Read aloud" control to each answer when speech output is available (idempotent on redraw).
  function decorate(){
    if (!canSpeak) return;
    document.querySelectorAll('.bubble .note').forEach(note => {
      const bubble = note.closest('.bubble');
      if (!bubble || bubble.querySelector('[data-action="read-aloud"]') || note.hasAttribute('data-live-answer')) return;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'small-button read-aloud'; b.dataset.action = 'read-aloud';
      b.setAttribute('aria-label', 'Read the first three lines aloud'); b.textContent = '🔊 Read aloud';
      note.insertAdjacentElement('afterend', b);
    });
  }
  decorate();
  new MutationObserver(decorate).observe(document.getElementById('app') || document.body, {childList: true, subtree: true});
  window.THREADPILOT_VOICE = {canListen, canSpeak, canRecord, normalizeSpoken};
})();
