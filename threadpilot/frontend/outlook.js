/* Send an email from the manager's own Outlook mailbox through Microsoft Graph.
 *
 * The browser signs in to Microsoft (MSAL, authorization code with PKCE; no secret anywhere) and calls Graph itself, so the
 * ThreadPilot server never sees a Microsoft password or token. The only permission asked for is Mail.Send: send mail as the
 * signed-in user. It cannot read, delete or move mail. Sent mail lands in the user's Sent Items like any other email.
 *
 * Set up once: register an app in Microsoft Entra and put its client ID in config.js (docs/outlook_setup.md).
 * Without a client ID, configured() is false and the email dialog opens Outlook on the web in a new window instead, with
 * everything filled in (webCompose; on phones, the Outlook app through mailto), and the manager presses Send there.
 */
(function () {
  const SCOPES = ['Mail.Send'];
  const GRAPH_SEND = 'https://graph.microsoft.com/v1.0/me/sendMail';
  const settings = () => (window.THREADPILOT_CONFIG && window.THREADPILOT_CONFIG.outlook) || {};
  const configured = () => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(settings().clientId || '');
  let ready = null;          // one MSAL client per page
  let interactive = false;   // set when a silent sign-in used up the click, so the next click opens the window at once

  class OutlookError extends Error {
    constructor(code, message, maybeSent = false) { super(message); this.code = code; this.maybeSent = maybeSent; }
  }

  function loadLibrary() {
    if (window.msal) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = new URL('vendor/msal-browser.min.js', document.baseURI).href;
      script.onload = resolve;
      script.onerror = () => reject(new OutlookError('load', 'Could not load Microsoft sign-in. Check the connection and try again. Nothing was sent.'));
      document.head.appendChild(script);
    });
  }

  function client() {
    if (!configured()) return Promise.reject(new OutlookError('not_configured', 'Sending from Outlook is not set up on this site yet.'));
    if (!ready) {
      ready = (async () => {
        await loadLibrary();
        const app = new window.msal.PublicClientApplication({
          auth: {
            clientId: settings().clientId,
            authority: 'https://login.microsoftonline.com/' + encodeURIComponent(settings().tenant || 'common'),
            redirectUri: new URL('auth-redirect.html', document.baseURI).href,
          },
          // Kept in this browser so the manager signs in once, not every morning. "Use another account" clears it.
          cache: {cacheLocation: 'localStorage'},
          // MSAL cannot see the sign-in window being closed (Microsoft's pages isolate it), so it waits this long for an
          // answer. Five minutes leaves time for a password and a phone prompt; pressing Send again starts over at once.
          system: {popupBridgeTimeout: 300000},
        });
        await app.initialize();
        return app;
      })().catch(error => { ready = null; throw error; });
    }
    return ready;
  }

  const current = app => app.getActiveAccount() || app.getAllAccounts()[0] || null;

  function explain(error) {
    const code = (error && (error.errorCode || error.code)) || '';
    const text = String((error && (error.errorMessage || error.message)) || '');
    if (code === 'popup_window_error' || code === 'empty_window_error') {
      interactive = true;
      return new OutlookError(code, 'The browser blocked the Microsoft sign-in window. Allow pop-ups for this site, then press Send again. Nothing was sent.');
    }
    if (code === 'interaction_in_progress_cancelled') return new OutlookError('superseded', 'Replaced by a newer sign-in.');
    if (code === 'user_cancelled') return new OutlookError(code, 'Microsoft sign-in was closed. Nothing was sent.');
    if (code === 'interaction_in_progress') return new OutlookError(code, 'A Microsoft sign-in window is already open. Finish it, then press Send again.');
    if (code === 'timed_out' || code === 'monitor_window_timeout') return new OutlookError(code, 'Microsoft sign-in took too long. Nothing was sent. Press Send again.');
    if (code === 'consent_required' || code === 'access_denied' || /AADSTS65001|AADSTS90094|admin/i.test(text))
      return new OutlookError('consent', 'Your Microsoft account did not allow ThreadPilot to send email. A work or school account may need IT to approve the app. Nothing was sent.');
    return new OutlookError(code || 'sign_in', 'Could not sign in to Microsoft. Nothing was sent. ' + text.split('\n')[0].slice(0, 200));
  }

  /** Get a token to send mail. Call it first thing in the click handler: only a click may open the sign-in window. */
  async function signIn() {
    const app = await client();
    const account = current(app);
    if (account && !interactive) {
      const started = Date.now();
      try {
        return await app.acquireTokenSilent({scopes: SCOPES, account});
      } catch (error) {
        // A slow silent attempt can use up the click; the window opened below may then be blocked, and the next click
        // goes straight to the window instead of failing the same way again.
        if (Date.now() - started > 3000) interactive = true;
      }
    }
    try {
      // overrideInteractionInProgress: a second press of Send abandons a sign-in window the manager closed or lost.
      const result = await app.acquireTokenPopup({scopes: SCOPES, overrideInteractionInProgress: true,
        ...(account ? {account} : {prompt: 'select_account'})});
      app.setActiveAccount(result.account);
      interactive = false;
      return result;
    } catch (error) { throw explain(error); }
  }

  /** Send a plain-text email. Resolves with {from} only when Outlook accepted it (HTTP 202). */
  async function send(auth, {to, cc = [], subject, body}) {
    const people = list => list.map(address => ({emailAddress: {address}}));
    let response;
    try {
      response = await fetch(GRAPH_SEND, {
        method: 'POST',
        headers: {Authorization: 'Bearer ' + auth.accessToken, 'Content-Type': 'application/json'},
        body: JSON.stringify({
          message: {subject, body: {contentType: 'Text', content: body}, toRecipients: people(to), ccRecipients: people(cc)},
          saveToSentItems: true,
        }),
      });
    } catch {
      throw new OutlookError('network', 'Could not reach Outlook. Check Sent Items in Outlook before sending again.', true);
    }
    if (response.status === 202) return {from: (auth.account && auth.account.username) || ''};
    let detail = '';
    try { detail = ((await response.json()).error || {}).message || ''; } catch { /* no JSON body */ }
    if (response.status === 401) { interactive = true; throw new OutlookError('expired', 'Your Microsoft sign-in has expired. Press Send again to sign in. Nothing was sent.'); }
    if (response.status === 403) throw new OutlookError('forbidden', 'This Microsoft account is not allowed to send email from ThreadPilot. Nothing was sent. ' + detail);
    if (response.status === 400) throw new OutlookError('rejected', 'Outlook rejected the email. Check the addresses. Nothing was sent. ' + detail);
    if (response.status === 429) throw new OutlookError('throttled', 'Outlook is limiting sends right now. Wait a minute and try again. Nothing was sent.');
    throw new OutlookError('server', `Outlook returned an error (${response.status}). Check Sent Items in Outlook before sending again.`, true);
  }

  /** The signed-in address, or '' (loads the library only when sending is set up). */
  async function account() {
    if (!configured()) return '';
    try { const found = current(await client()); return (found && found.username) || ''; } catch { return ''; }
  }

  /** Forget the Microsoft sign-in in this browser (it does not sign the user out of Microsoft elsewhere). */
  async function forget() {
    const app = await client();
    const found = current(app);
    app.setActiveAccount(null);
    if (found) await app.clearCache({account: found});
  }

  /** Outlook on the web's "new message" address with everything filled in (no app registration needed). The manager
   *  presses Send in Outlook. web: 'office' for work or school Microsoft 365 mailboxes, 'live' for Outlook.com/Hotmail. */
  function webCompose({to, cc = [], subject, body}) {
    const base = settings().web === 'live' ? 'https://outlook.live.com/mail/0/deeplink/compose'
      : 'https://outlook.office.com/mail/deeplink/compose';
    const join = list => list.map(encodeURIComponent).join(',');
    const query = ['to=' + join(to), cc.length ? 'cc=' + join(cc) : '', 'subject=' + encodeURIComponent(subject),
      'body=' + encodeURIComponent(body.replace(/\r?\n/g, '\r\n'))].filter(Boolean).join('&');
    return base + '?' + query;
  }

  /** mailto: link for the fallback: opens Outlook (or the default mail app) with everything filled in. */
  function mailto({to, cc = [], subject, body}) {
    const join = list => list.map(encodeURIComponent).join(',');
    const query = [cc.length ? 'cc=' + join(cc) : '', 'subject=' + encodeURIComponent(subject),
      'body=' + encodeURIComponent(body.replace(/\r?\n/g, '\r\n'))].filter(Boolean).join('&');
    return 'mailto:' + join(to) + '?' + query;
  }

  window.ThreadPilotOutlook = {configured, signIn, send, account, forget, webCompose, mailto, OutlookError};
})();
