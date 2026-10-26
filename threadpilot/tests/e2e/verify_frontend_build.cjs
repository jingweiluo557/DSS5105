const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
function build(value) {
  return spawnSync(process.execPath, ['deploy/build_frontend.cjs'], {
    cwd: root, encoding: 'utf8', env: {...process.env, THREADPILOT_PUBLIC_API_BASE: value}
  });
}
for (const value of ['', 'http://api.example.com', 'https://localhost',
  'https://127.0.0.1', 'https://[::1]', 'https://user:password@api.example.com',
  'https://api.example.com/api', 'https://api.example.com/?token=private']) {
  assert.notEqual(build(value).status, 0, 'Invalid origin accepted: ' + value);
}
assert.equal(build('https://api.example.com/').status, 0);
const output = path.join(root, 'dist/frontend');
for (const file of ['index.html', 'briefing.html', 'chat-layout.css', 'briefing.js'])
  assert(fs.existsSync(path.join(output, file)), 'Missing asset: ' + file);
assert(!fs.existsSync(path.join(output, 'README_ZH.md')));
const context = {URL, location: new URL('https://frontend.example.com'), window: {}};
vm.runInNewContext(fs.readFileSync(path.join(output, 'config.js'), 'utf8'), context);
assert.equal(context.window.THREADPILOT_API_BASE, 'https://api.example.com');
assert.equal(context.window.THREADPILOT_CONFIG_ERROR, undefined);
console.log('PASS: CloudBase static build injects public backend, copies UI assets and rejects invalid origins.');
