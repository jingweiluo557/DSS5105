/* Shared authenticated transport. Only the configured backend receives the access key. */
(() => {
  if(window.THREADPILOT_CONFIG_ERROR)return;
  const base = new URL(window.THREADPILOT_API_BASE);
  const storageKey = 'threadpilot-access:' + base.origin;
  const nameKey = 'threadpilot-name:' + base.origin;
  let displayName = '';
  try { displayName = sessionStorage.getItem(nameKey) || ''; } catch {}
  window.threadpilotName = () => displayName;
  let token = '';
  try { token = sessionStorage.getItem(storageKey) || ''; } catch {}
  const allowed = input => {
    const url = new URL(input, location.href);
    if (url.origin !== base.origin || !(url.pathname.startsWith('/api/') || url.pathname === '/chat'))
      throw new Error('This address is not a ThreadPilot API endpoint.');
    return url;
  };
  function clearConversation() {
    for (const key of ['threadpilot-workflow-session', 'threadpilot-llm-chat', 'threadpilot-review-context']) sessionStorage.removeItem(key);
    localStorage.removeItem('threadpilot-track1-v2');
  }
  const backendKey='threadpilot-backend-origin';
  if(sessionStorage.getItem(backendKey)&&sessionStorage.getItem(backendKey)!==base.origin)clearConversation();
  sessionStorage.setItem(backendKey,base.origin);
  function showAccess() {
    if (document.getElementById('access-dialog')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'access-dialog';
    dialog.className = 'access-dialog';
    dialog.setAttribute('aria-labelledby', 'access-title');
    dialog.innerHTML = `<form><div class="eyebrow">THREADPILOT</div><h2 id="access-title">Connect to your workspace</h2>
      <p>Enter the workspace access key provided by your administrator. It stays in this browser tab.</p>
      <label class="field">Your name<input name="display-name" autocomplete="name" required maxlength="100"></label>
      <p class="muted">Your name identifies the records you save. Access is still controlled by the workspace key.</p>
      <label class="field">Workspace access key<input name="access-key" type="password" autocomplete="off" required maxlength="256"></label>
      <p role="alert"></p><button class="primary" type="submit">Connect</button></form>`;
    dialog.addEventListener('cancel', e => e.preventDefault());
    dialog.querySelector('form').addEventListener('submit', async e => {
      e.preventDefault();
      const button = dialog.querySelector('button');
      const error = dialog.querySelector('[role=alert]');
      const candidate = dialog.querySelector('[name="access-key"]').value.trim();
      const name = dialog.querySelector('[name="display-name"]').value.trim();
      if (!name) { error.textContent = 'Enter your name.'; return; }
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
        if (candidate !== token || name !== displayName) clearConversation();
        sessionStorage.setItem(storageKey, candidate);
        sessionStorage.setItem(nameKey, name);
        location.reload();
      } catch (err) {
        error.textContent = err instanceof TypeError ? 'Cannot connect. Check the backend address and allowed website origin.' : err.message;
        button.disabled = false;
      }
    });
    document.body.append(dialog);
    dialog.querySelector('[name="display-name"]').value = displayName;
    dialog.querySelector('[name="access-key"]').value = token;
    dialog.showModal();
  }
  window.threadpilotFetch = async (input, options = {}) => {
    const url = allowed(input);
    const headers = new Headers(options.headers);
    if (token) headers.set('X-ThreadPilot-Token', token);
    if (displayName) headers.set('X-ThreadPilot-Name', encodeURIComponent(displayName));
    if (token && !displayName) showAccess();
    const response = await fetch(url.href, {...options, headers, credentials: 'include', redirect: 'error'});
    if (response.status === 401 && !headers.has('Authorization')) showAccess();
    return response;
  };
  window.threadpilotSignOut = () => {
    sessionStorage.removeItem(storageKey);
    sessionStorage.removeItem(nameKey);
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
