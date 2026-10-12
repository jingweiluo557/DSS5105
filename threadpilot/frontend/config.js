/* Public configuration only. Never put database passwords or API keys here.
 * For GitHub Pages, set apiBase to the CloudBase HTTPS service origin.
 * Empty means same-origin; port 8765 keeps the local development proxy target.
 */
const localFrontend = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
window.THREADPILOT_CONFIG = {apiBase: localFrontend ? '' :
  'https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com',
  /* "Send with Outlook" on the morning email. clientId is the Application (client) ID of the team's Microsoft Entra app
   * registration (public, not a secret; see docs/outlook_setup.md). Empty: the button opens Outlook in a window instead.
   * tenant: 'common' (any work, school or personal Microsoft account), 'consumers', 'organizations', or a tenant ID.
   * web: which Outlook the "Open in Outlook" window uses when clientId is empty: 'office' (work or school Microsoft 365)
   * or 'live' (Outlook.com / Hotmail). */
  outlook: {clientId: '', tenant: 'common', web: 'office'}};
window.THREADPILOT_API_BASE = (window.THREADPILOT_CONFIG.apiBase ||
  (location.port === '8765' ? 'http://127.0.0.1:8000' : location.origin)).replace(/\/+$/, '');
