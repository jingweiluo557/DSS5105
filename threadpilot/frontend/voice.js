/* Voice in / voice out for a manager on the floor.
   Voice in: tap ♩ and speak. The browser's own speech recognition listens when it has one (Chrome, Edge, Safari);
   otherwise the page records a short clip and the server transcribes it (POST /api/v1/voice/transcribe, nothing stored).
   Spoken order numbers are cleaned up ("O R D zero zero five" → ORD-005), and the question is sent as soon as you stop
   speaking. One exception, on purpose: a confirmation ("send now", "confirm", "save it") is never sent by voice. It is
   put in the box and waits for a tap, so a misheard word can never send an email.
   If the browser's recognition fails (no speech service on the phone, an in-app browser), the next tap records instead.
   Voice out: an answer to a spoken question is read aloud (its first three lines); every answer has a "Read aloud" button;
   and the speaker button beside the microphone turns spoken replies on for every answer (remembered in this browser).
   Replies are spoken in the answer's language. Phones only allow speech that starts from a tap, so the first tap on the
   microphone or the speaker button unlocks it for answers that arrive later. */
(function(){
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let canListen = !!Recognition; const canSpeak = 'speechSynthesis' in window;
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
  let voiceAsked = false, recognizer = null, recorder = null, unlocked = false;
  const MIC = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
  const STOP = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>';
  const SPEAKER = on => '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/>' + (on ? '<path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>' : '<path d="M17 9l5 6M22 9l-5 6"/>') + '</svg>';
  const speakOn = () => !!(typeof state === 'object' && state.settings && state.settings.speak);
  // A phone only speaks after a tap; a silent utterance inside the tap unlocks later, automatic replies.
  function unlock(){
    if (!canSpeak || unlocked) return; unlocked = true;
    try { const u = new SpeechSynthesisUtterance(' '); u.volume = 0; window.speechSynthesis.speak(u); } catch {}
  }
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
    button.innerHTML = on ? STOP : MIC;
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
    recognizer.onerror = e => {
      text = '';
      if (['network', 'service-not-allowed', 'language-not-supported', 'audio-capture'].includes(e.error) && canRecord && e.error !== 'audio-capture') { canListen = false; say('This browser\u2019s speech service is not available. Tap the microphone again to record your question instead.'); return; }
      say(e.error === 'not-allowed' ? 'Microphone access was refused.' : e.error === 'no-speech' ? 'Nothing heard; tap the microphone and try again.' : 'Could not hear that; try again.');
    };
    recognizer.onend = () => { recognizer = null; setListening(button, false); finish(button, text); };
    try { recognizer.start(); }
    catch (err) { recognizer = null; setListening(button, false); if (canRecord) { canListen = false; record(button); } else say('Voice input could not start in this browser. Type the question instead.'); }
  }
  async function record(button){
    if (recorder) { recorder.stop(); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({audio: true}); }
    catch (err) { say(err && err.name === 'NotFoundError' ? 'No microphone found on this device.' : 'Microphone access was refused. Allow it in the browser\u2019s site settings, or type the question.'); return; }
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
        const data = await r.json().catch(() => ({}));
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
  function voiceFor(lang){
    const voices = (window.speechSynthesis.getVoices && window.speechSynthesis.getVoices()) || [];
    const base = lang.slice(0, 2).toLowerCase();
    return voices.find(v => v.lang && v.lang.replace('_', '-').toLowerCase() === lang.toLowerCase()) || voices.find(v => v.lang && v.lang.toLowerCase().startsWith(base)) || null;
  }
  // Spoken form: order numbers digit by digit, ISO dates as dates, no table pipes or arrows.
  function spokenForm(text, zh){
    return text.replace(/\bORD-(\d)(\d)(\d)\b/g, zh ? '订单 $1 $2 $3' : 'order $1 $2 $3').replace(/\u2192|->/g, zh ? '到' : ' to ').replace(/\s*[\u2014\u2013]\s*/g, ', ').replace(/\s{2,}/g, ' ');
  }
  function speakText(text, button){
    if (!canSpeak || !text) return;
    const lead = firstLines(text); if (!lead) return;
    const zh = /[\u4e00-\u9fff]/.test(lead), lang = zh ? 'zh-CN' : 'en-SG';
    window.speechSynthesis.cancel();
    // Short sentences one at a time: some browsers cut off a long single utterance.
    const parts = spokenForm(lead, zh).match(/[^.!?。！？;；]+[.!?。！？;；]*/g) || [lead];
    const voice = voiceFor(lang) || (zh ? null : voiceFor('en-GB') || voiceFor('en-US'));
    parts.map(t => t.trim()).filter(Boolean).forEach((t, i, all) => {
      const utter = new SpeechSynthesisUtterance(t);
      utter.lang = voice ? voice.lang : lang; if (voice) utter.voice = voice; utter.rate = 1.0;
      if (i === all.length - 1) utter.onend = utter.onerror = () => resetReadButtons();
      window.speechSynthesis.speak(utter);
    });
    if (button) { button.textContent = '\u25a0 Stop'; button.dataset.speaking = '1'; }
  }
  function resetReadButtons(){
    document.querySelectorAll('[data-action="read-aloud"][data-speaking]').forEach(b => { b.textContent = '\ud83d\udd0a Read aloud'; delete b.dataset.speaking; });
  }
  function speak(button){
    if (!canSpeak) return;
    const mine = button.dataset.speaking === '1';
    window.speechSynthesis.cancel(); resetReadButtons();
    if (mine) return;
    const bubble = button.closest('.bubble');
    const note = bubble && bubble.querySelector('.note');
    speakText(note ? note.textContent : '', button);
  }
  function toggleReplies(){
    if (typeof state !== 'object') return;
    state.settings = {...state.settings, speak: !speakOn()};
    if (typeof save === 'function') save();
    if (speakOn()) { unlock(); say('Spoken replies on: each answer is read aloud.'); } else { window.speechSynthesis.cancel(); resetReadButtons(); say('Spoken replies off.'); }
    document.querySelectorAll('[data-action="voice-replies"]').forEach(paintReplies);
  }
  function paintReplies(b){
    const on = speakOn();
    b.innerHTML = SPEAKER(on); b.setAttribute('aria-pressed', String(on)); b.classList.toggle('on', on);
    b.setAttribute('aria-label', on ? 'Spoken replies are on. Tap to turn off' : 'Spoken replies are off. Tap to turn on'); b.title = on ? 'Spoken replies: on' : 'Spoken replies: off';
  }
  // An answer to a spoken question is read aloud when it arrives.
  if (typeof ask === 'function') {
    const textAsk = ask;
    ask = async function(question){
      const spoken = voiceAsked; voiceAsked = false;
      const before = (state.chat || []).length;
      await textAsk(question);
      const answer = (state.chat || []).slice(before).reverse().find(m => m.role === 'assistant');
      if ((spoken || speakOn()) && answer) speakText(answer.text);
    };
  }
  document.addEventListener('submit', () => { if (speakOn()) unlock(); }, true);
  // Capture phase so this runs before app.js's demo handler for the same button.
  document.addEventListener('click', e => {
    const voice = e.target.closest('[data-action="voice"]');
    if (voice && (canListen || canRecord)) { e.preventDefault(); e.stopImmediatePropagation(); unlock(); canListen ? listen(voice) : record(voice); return; }
    const replies = e.target.closest('[data-action="voice-replies"]');
    if (replies) { e.preventDefault(); e.stopImmediatePropagation(); toggleReplies(); return; }
    const read = e.target.closest('[data-action="read-aloud"]');
    if (read) { e.preventDefault(); e.stopImmediatePropagation(); speak(read); }
  }, true);
  // Add a "Read aloud" control to each answer when speech output is available (idempotent on redraw).
  function decorate(){
    // The microphone gets a proper icon and a name; a speaker toggle sits beside it.
    document.querySelectorAll('[data-action="voice"]:not([data-voice-ready])').forEach(b => {
      b.dataset.voiceReady = '1'; b.classList.add('voice-button'); b.type = 'button';
      if (!(canListen || canRecord)) { b.hidden = true; }
      else { b.innerHTML = MIC; b.setAttribute('aria-label', 'Speak your question'); b.title = 'Speak your question'; }
      if (canSpeak && !b.parentElement.querySelector('[data-action="voice-replies"]')) {
        const t = document.createElement('button'); t.type = 'button'; t.className = 'voice-button voice-replies'; t.dataset.action = 'voice-replies';
        paintReplies(t); b.insertAdjacentElement('afterend', t);
      }
    });
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
  window.THREADPILOT_VOICE = {get canListen(){ return canListen; }, canSpeak, canRecord, normalizeSpoken, speakText};
})();
