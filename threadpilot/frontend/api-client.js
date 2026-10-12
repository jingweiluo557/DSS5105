/* Shared authenticated transport. Only the configured backend receives the access key. */
(() => {
  const base = new URL(window.THREADPILOT_API_BASE);
  const storageKey = 'threadpilot-access:' + base.origin;
  let token = '';
  try { token = sessionStorage.getItem(storageKey) || ''; } catch {}
  const allowed = input => {
    const url = new URL(input, location.href);
    if (url.origin !== base.origin || !(url.pathname.startsWith('/api/') || url.pathname === '/chat'))
      throw new Error('This address is not a ThreadPilot API endpoint.');
    return url;
  };
  function clearConversation() {
    for (const key of ['threadpilot-workflow-session', 'threadpilot-llm-chat']) sessionStorage.removeItem(key);
    localStorage.removeItem('threadpilot-track1-v2');
  }
  function showAccess() {
    if (document.getElementById('access-dialog')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'access-dialog';
    dialog.className = 'access-dialog';
    dialog.setAttribute('aria-labelledby', 'access-title');
    dialog.innerHTML = `<form><div class="eyebrow">THREADPILOT</div><h2 id="access-title">Connect to your workspace</h2>
      <p>Enter the workspace access key provided by your administrator. It stays in this browser tab.</p>
      <label class="field">Workspace access key<input name="access-key" type="password" autocomplete="off" required maxlength="256"></label>
      <p role="alert"></p><button class="primary" type="submit">Connect</button></form>`;
    dialog.addEventListener('cancel', e => e.preventDefault());
    dialog.querySelector('form').addEventListener('submit', async e => {
      e.preventDefault();
      const button = dialog.querySelector('button');
      const error = dialog.querySelector('[role=alert]');
      const candidate = dialog.querySelector('input').value.trim();
      button.disabled = true;
      error.textContent = '';
      try {
        const response = await fetch(base.origin + '/api/snapshot', {
          headers: {'X-ThreadPilot-Token': candidate}, cache: 'no-store', redirect: 'error'
        });
        if (response.status === 401) throw new Error('The access key was not accepted. Please try again.');
        if (!response.ok) throw new Error('The workspace is unavailable. Please try again shortly.');
        const snapshot = await response.json();
        if (!Array.isArray(snapshot.orders)) throw new Error('The backend did not return workspace data.');
        if (candidate !== token) clearConversation();
        sessionStorage.setItem(storageKey, candidate);
        location.reload();
      } catch (err) {
        error.textContent = err instanceof TypeError ? 'Cannot connect. Check the backend address and allowed website origin.' : err.message;
        button.disabled = false;
      }
    });
    document.body.append(dialog);
    dialog.showModal();
  }
  window.threadpilotFetch = async (input, options = {}) => {
    const url = allowed(input);
    const headers = new Headers(options.headers);
    if (token) headers.set('X-ThreadPilot-Token', token);
    const response = await fetch(url.href, {...options, headers, redirect: 'error'});
    if (response.status === 401) showAccess();
    return response;
  };
  window.threadpilotSignOut = () => {
    sessionStorage.removeItem(storageKey);
    clearConversation();
    location.reload();
  };
  // Normal hyperlinks cannot carry authentication headers. Display API records safely in a dialog.
  document.addEventListener('click', async e => {
    if (e.target.closest('[data-action="disconnect-workspace"]')) {
      e.preventDefault(); window.threadpilotSignOut(); return;
    }
    const link = e.target.closest('a[href]');
    if (!link) return;
    let url;
    try { url = allowed(link.href); } catch { return; }
    e.preventDefault();
    const dialog = document.createElement('dialog');
    dialog.className = 'record-dialog';
    dialog.innerHTML = '<button type="button" aria-label="Close record">Close</button><h2>Current database record</h2><pre>Loading…</pre>';
    dialog.querySelector('button').addEventListener('click', () => dialog.close());
    document.body.append(dialog);
    dialog.addEventListener('close', () => dialog.remove());
    dialog.showModal();
    try {
      const response = await window.threadpilotFetch(url.href);
      if (response.status === 401) { dialog.close(); return; }
      if (!response.ok) throw new Error('Unable to load this record. Please try again.');
      dialog.querySelector('pre').textContent = JSON.stringify(await response.json(), null, 2);
    } catch (err) { dialog.querySelector('pre').textContent = err.message; }
  });
})();
