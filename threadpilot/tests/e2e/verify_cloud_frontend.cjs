/* Real browser -> CloudBase gateway -> MySQL/model. No mocked API responses.
 * Reads the private local configuration; never writes access keys to reports. */
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const frontend = path.join(root, 'frontend');
const config = JSON.parse(fs.readFileSync(path.join(root, 'backend/.env.cloudfunction.json'), 'utf8'));
const backend = process.env.LIVE_API_ORIGIN || 'https://dss5105-track1-i7gxvcy5k7ef5ac9b-1500904749.ap-singapore.app.tcloudbase.com';
const output = path.join(root, 'backend/runtime/cloud-frontend');
fs.mkdirSync(output, {recursive:true});
const report = {checks:[], errors:[], passed:false};
(async () => {
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (pathname === '/config.js') {
      res.setHeader('Content-Type','application/javascript');
      return res.end('window.THREADPILOT_API_BASE=' + JSON.stringify(backend) + ';');
    }
    const file = path.resolve(frontend, '.' + (pathname === '/' ? '/index.html' : pathname));
    if (!file.startsWith(frontend + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404); return res.end();
    }
    res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise((resolve,reject) => {server.once('error',reject);server.listen(8765,'127.0.0.1',resolve);});
  let browser;
  try {
    browser = await chromium.launch({channel:'msedge',headless:true});
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    await page.addInitScript(() => {
      window.cloudTestFrames = [];
      const originalFetch = window.fetch;
      window.fetch = async (...args) => {
        const response = await originalFetch(...args);
        if (String(args[0]).endsWith('/api/v1/workflow/chat/stream')) {
          response.clone().text().then(raw => window.cloudTestFrames.push({status:response.status,raw}));
        }
        return response;
      };
    });
    page.setDefaultTimeout(100000);
    page.on('pageerror', e => report.errors.push(e.message));
    await page.goto('http://127.0.0.1:8765/#/ai');
    await page.locator('#access-dialog').waitFor();
    await page.getByLabel('Workspace access key',{exact:true}).fill('invalid-test-key');
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.locator('#access-dialog [role=alert]').filter({hasText:'not accepted'}).waitFor();
    report.checks.push('Missing/wrong access key blocked by real backend');
    await page.getByLabel('Workspace access key',{exact:true}).fill(config.API_ACCESS_TOKEN);
    await page.getByRole('button',{name:'Connect',exact:true}).click();
    await page.locator('.copilot-workspace').waitFor();
    assert.equal(await page.evaluate(() => TRACK1_DATA.orders.length),120);
    report.checks.push('Login and 120 live cloud orders loaded across origins');
    const send = async question => {
      await page.locator('[name=visible-question]').fill(question);
      const before = await page.evaluate(()=>window.cloudTestFrames.length);
      await page.locator('[data-form=chat] [type=submit]').click();
      await page.waitForFunction(n=>window.cloudTestFrames.length > n,before);
      const {raw,status} = await page.evaluate(()=>window.cloudTestFrames.at(-1));
      assert.equal(status,200);
      const frame = raw.split('\n\n').find(f=>f.startsWith('event: done'));
      assert(frame,'Missing done event');
      const result = JSON.parse(frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trim()).join('\n'));
      await page.waitForFunction(() => !aiBusy);
      return result;
    };
    const first = await send('Open order ORD-005 and show its current status.');
    assert.equal(first.state.active_order,'ORD-005');
    assert(first.evidence.length);
    report.checks.push('Real model workflow returned validated SSE and evidence');
    await page.locator('a.evidence-record').first().click();
    await page.waitForFunction(() => {const p=document.querySelector('.record-dialog pre');return p && p.textContent.includes('ORD-005');});
    await page.getByRole('button',{name:'Close record'}).click();
    report.checks.push('Authenticated evidence opens in the page');
    await page.reload();
    await page.locator('.copilot-workspace').waitFor();
    assert.equal(await page.evaluate(()=>workflowSession),first.state.session_id);
    const followup = await send('Refresh this order.');
    assert.equal(followup.state.session_id,first.state.session_id);
    assert.equal(followup.state.active_order,'ORD-005');
    report.checks.push('Reload and follow-up retain the cloud conversation');
    const status = await page.evaluate(async () => (await window.threadpilotFetch(window.THREADPILOT_API_BASE + '/api/v1/workflow/notifications/' + workflowSession)).status);
    assert.equal(status,200);
    report.checks.push('Authenticated notifications endpoint responds');
    await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right <= 0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    report.checks.push('Mobile layout fits viewport');
    await page.evaluate(()=>window.threadpilotSignOut());
    await page.locator('#access-dialog').waitFor();
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('threadpilot-workflow-session')),null);
    report.checks.push('Disconnect clears access and conversation');
    assert.deepEqual(report.errors,[]);
    report.passed = true;
    console.log('PASS:',report.checks.join('; '));
  } finally {
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
    if (browser) await browser.close();
    server.closeAllConnections();server.close();
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
