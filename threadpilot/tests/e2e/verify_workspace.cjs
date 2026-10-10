const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../../frontend');
const screenshots = process.env.WORKSPACE_SCREENSHOT_DIR || require('os').tmpdir();

(async () => {
  const requests = [];
  const server = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/api/snapshot') return res.end(fs.readFileSync(path.join(__dirname, 'snapshot.fixture.json')));
    if (req.url === '/api/v1/health') return res.end(JSON.stringify({configured:true, model:'fixture'}));
    if (req.url.startsWith('/api/evidence/')) return res.end(JSON.stringify({record_id:20}));
    if (req.url === '/api/v1/workflow/chat/stream') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        requests.push(JSON.parse(body));
        res.setHeader('Content-Type', 'text/event-stream');
        res.end('event: done\ndata: ' + JSON.stringify({answer:'Verified order result '+requests.length, state:{session_id:'session-1'}, confirmation_id:'confirmation-1', order_ids:['ORD-020'], selected_order_id:'ORD-020', sources:['orders'], evidence:[{url:'/api/evidence/orders/20',source:'orders',row:20}], business_date:'2026-04-01',model:'fixture'})+'\n\n');
      });
      return;
    }
    const file = path.join(root, req.url === '/' ? 'index.html' : req.url.split('?')[0]);
    if (!file.startsWith(root) || !fs.existsSync(file)) {res.writeHead(404); return res.end();}
    res.setHeader('Content-Type', file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage({viewport:{width:1600,height:1000}});
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/#/ai`);
    await page.locator('.copilot-workspace').waitFor();
    assert.equal(await page.locator('.sidebar nav a').count(),4);
    await page.getByRole('button',{name:'Generate daily report ↗'}).click();
    await page.getByText('Verified order result 1',{exact:true}).waitFor();
    await page.locator('[name=visible-question]').fill('Why this order?');
    await page.locator('[data-form=chat] [type=submit]').click();
    await page.getByText('Verified order result 2',{exact:true}).waitFor();
    assert.equal(requests[1].session_id,'session-1');
    assert.equal(requests[1].confirmation_id,'confirmation-1');
    assert.equal(await page.locator('.turn-list li').count(),2);
    assert.equal(await page.locator('.copilot-evidence').count(),0);
    assert.equal(await page.getByText('SOURCE RECORDS',{exact:true}).count(),0);
    assert.equal(await page.getByRole('heading',{name:'Conversation record',exact:true}).count(),1);
    assert.equal(await page.locator('.copilot-chat a[href$="/api/evidence/orders/20"]').count(),1);
    await page.locator('[data-action=jump-turn]').first().click();
    const downloadEvent=page.waitForEvent('download');
    await page.getByRole('button',{name:'Export conversation'}).click();
    const download=await downloadEvent;
    const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
    assert.equal(exported.messages.length,4);
    await page.screenshot({path:path.join(screenshots,'workspace-desktop.png'),fullPage:true});
    for(const route of ['orders','exceptions','risk','feasibility','messages']) {
      await page.locator(`.workspace-tools a[href="#/${route}"]`).click();
      await page.waitForFunction(route=>location.hash==='#/'+route,route);
      assert.equal(await page.locator('.sidebar a[href="#/ai"][aria-current=page]').count(),1);
    }
    for(const route of ['activity','settings']) {
      await page.locator(`.sidebar a[href="#/${route}"]`).click();
      await page.waitForFunction(route=>location.hash==='#/'+route,route);
      assert.equal(await page.locator(`.sidebar a[href="#/${route}"][aria-current=page]`).count(),1);
      assert.equal(await page.locator('.sidebar [aria-current=page]').count(),1);
      assert.equal(await page.locator('.workspace-tools').count(),0);
    }
    await page.locator('.sidebar a[href="#/ai"]').click();
    await page.setViewportSize({width:390,height:844});
    await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile horizontal overflow');
    await page.screenshot({path:path.join(screenshots,'workspace-mobile.png'),fullPage:true});
    await page.locator('[data-action=new-chat]').click();
    await page.locator('[name=visible-question]').fill('Start again');
    await page.locator('[data-form=chat] [type=submit]').click();
    await page.getByText('Verified order result 3',{exact:true}).waitFor();
    assert.equal(requests[2].session_id,null);
    assert.equal(requests[2].confirmation_id,null);
    assert.deepEqual(errors,[]);
    console.log('PASS: unified navigation, daily report, session/confirmation continuity, per-turn evidence, export, tools, mobile layout, new session.');
  } finally {
    await browser.close();server.closeAllConnections();server.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
