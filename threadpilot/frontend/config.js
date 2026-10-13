/* Public configuration only. Never put database passwords or API keys here.
 * For GitHub Pages, set apiBase to the CloudBase HTTPS service origin.
 * Empty means same-origin; port 8765 keeps the local development proxy target.
 */
window.THREADPILOT_CONFIG = window.THREADPILOT_CONFIG || {apiBase: ''};
window.THREADPILOT_API_BASE = (window.THREADPILOT_CONFIG.apiBase ||
  (location.port === '8765' ? 'http://127.0.0.1:8000' : location.origin)).replace(/\/+$/, '');
