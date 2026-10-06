/* Public configuration only. Never put database passwords or API keys here.
 * For GitHub Pages, set apiBase to the CloudBase HTTPS service origin.
 * Empty means same-origin; port 8765 keeps the local development proxy target.
 */
const localFrontend = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
window.THREADPILOT_CONFIG = {apiBase: localFrontend ? '' :
  'https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com'};
window.THREADPILOT_API_BASE = (window.THREADPILOT_CONFIG.apiBase ||
  (location.port === '8765' ? 'http://127.0.0.1:8000' : location.origin)).replace(/\/+$/, '');
