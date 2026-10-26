/* Dependency-free static build for CloudBase Git deployments. Public URL only. */
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const source = path.join(root, 'frontend');
const output = path.join(root, 'dist', 'frontend');
const value = (process.env.THREADPILOT_PUBLIC_API_BASE || '').trim();
let backend;
try {
  backend = new URL(value);
  if (backend.protocol !== 'https:' || backend.username || backend.password ||
      backend.search || backend.hash || backend.pathname !== '/' ||
      backend.hostname === 'localhost' || backend.hostname.endsWith('.localhost') ||
      backend.hostname === '[::1]' || /^127\./.test(backend.hostname)) throw Error();
} catch {
  console.error('Set THREADPILOT_PUBLIC_API_BASE to the public HTTPS backend origin, without a path or credentials.');
  process.exit(1);
}

const allowed = new Set(['.html', '.js', '.css', '.png', '.svg', '.jpg', '.webp', '.ico', '.woff', '.woff2']);
function copy(directory, relative = '') {
  for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
    if (entry.name.startsWith('.') || entry.isSymbolicLink()) continue;
    const next = path.join(relative, entry.name);
    if (entry.isDirectory()) { copy(path.join(directory, entry.name), next); continue; }
    if (!entry.isFile() || !allowed.has(path.extname(entry.name))) continue;
    const target = path.join(output, next);
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.copyFileSync(path.join(directory, entry.name), target);
  }
}
copy(source);
const config = fs.readFileSync(path.join(source, 'config.js'), 'utf8');
fs.writeFileSync(path.join(output, 'config.js'),
  'window.THREADPILOT_CONFIG = ' + JSON.stringify({apiBase: backend.origin}) + ';\n' + config);
console.log('Static frontend prepared in dist/frontend. Backend: ' + backend.origin);
