/* Public configuration only. Never put database passwords or API keys here.
 * For GitHub Pages, set apiBase to the CloudBase HTTPS service origin.
 * Empty always means same-origin, including LAN and mobile visitors.
 */
window.THREADPILOT_CONFIG = window.THREADPILOT_CONFIG || {apiBase: ''};
(() => {
 try {
  const configured = window.THREADPILOT_CONFIG.apiBase?.trim();
  const base = new URL(configured || location.origin, location.origin);
  const loopback = name => name === 'localhost' || name === '[::1]' || /^127\./.test(name);
  if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password ||
      base.search || base.hash || !['', '/'].includes(base.pathname))
    throw new Error('Backend must be an HTTP(S) origin without a path, query or credentials.');
  if (!loopback(location.hostname) && loopback(base.hostname))
    throw new Error('A remote browser cannot use a loopback backend. Configure the server LAN/HTTPS origin.');
  if (location.protocol === 'https:' && base.protocol !== 'https:')
    throw new Error('An HTTPS website requires an HTTPS backend.');
  window.THREADPILOT_API_BASE = base.origin;
 } catch(error) { window.THREADPILOT_CONFIG_ERROR=error.message; }
})();
