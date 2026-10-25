/* Voice in / voice out for a manager on the floor. Browser-native only (Web Speech API): no audio leaves the page
   except through the browser's own speech service, nothing is recorded, and both features degrade to the existing
   demo transcript dialog when the browser has no speech support (Firefox, some in-app browsers).
   Voice in: the ♩ button fills the composer with what was said and focuses the textarea; sending stays a tap.
   Voice out: a "Read aloud" button on each answer speaks its first three lines, then stops. */
(function(){
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canListen = !!Recognition, canSpeak = 'speechSynthesis' in window;
  let recognizer = null;
  function listen(button){
    const form = button.closest('form');
    const area = form && form.querySelector('textarea[name="visible-question"]');
    if (!area) return;
    if (recognizer) { recognizer.stop(); return; }
    recognizer = new Recognition();
    recognizer.lang = navigator.language && navigator.language.startsWith('zh') ? navigator.language : 'en-SG';
    recognizer.interimResults = true; recognizer.maxAlternatives = 1;
    button.classList.add('listening'); button.setAttribute('aria-pressed', 'true');
    area.placeholder = 'Listening… speak your question';
    recognizer.onresult = e => { area.value = Array.from(e.results).map(r => r[0].transcript).join(' ').trim(); };
    recognizer.onerror = e => { if (typeof toast === 'function') toast(e.error === 'not-allowed' ? 'Microphone access was refused.' : 'Could not hear that; try again.'); };
    recognizer.onend = () => { recognizer = null; button.classList.remove('listening'); button.removeAttribute('aria-pressed'); area.placeholder = 'Ask about an order, a risk, or your next move…'; if (area.value.trim()) area.focus(); };
    try { recognizer.start(); } catch (err) { recognizer = null; }
  }
  function firstLines(text, n = 3){
    return String(text || '').replace(/[*_`#>|]/g, ' ').split(/\n+/).map(l => l.trim()).filter(Boolean).slice(0, n).join('. ');
  }
  function speak(button){
    if (!canSpeak) return;
    if (window.speechSynthesis.speaking) { window.speechSynthesis.cancel(); return; }
    const bubble = button.closest('.bubble');
    const note = bubble && bubble.querySelector('.note');
    const utter = new SpeechSynthesisUtterance(firstLines(note ? note.textContent : ''));
    utter.lang = 'en-SG'; utter.rate = 1.0;
    window.speechSynthesis.speak(utter);
  }
  // Capture phase so this runs before app.js's demo handler for the same button; stop propagation only when supported.
  document.addEventListener('click', e => {
    const voice = e.target.closest('[data-action="voice"]');
    if (voice && canListen) { e.preventDefault(); e.stopImmediatePropagation(); listen(voice); return; }
    const read = e.target.closest('[data-action="read-aloud"]');
    if (read) { e.preventDefault(); e.stopImmediatePropagation(); speak(read); }
  }, true);
  // Add a "Read aloud" control to each answer when speech output is available (idempotent on redraw).
  function decorate(){
    if (!canSpeak) return;
    document.querySelectorAll('.bubble .note').forEach(note => {
      const bubble = note.closest('.bubble');
      if (!bubble || bubble.querySelector('[data-action="read-aloud"]')) return;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'small-button read-aloud'; b.dataset.action = 'read-aloud';
      b.setAttribute('aria-label', 'Read the first three lines aloud'); b.textContent = '🔊 Read aloud';
      note.insertAdjacentElement('afterend', b);
    });
  }
  decorate();
  new MutationObserver(decorate).observe(document.getElementById('app') || document.body, {childList: true, subtree: true});
  window.THREADPILOT_VOICE = {canListen, canSpeak};
})();
