const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require('playwright');
const snapshot = require('./snapshot.fixture.json');
const risk = require('./queue.fixture.cjs');

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage();
    const records = [{id:'watch-1',kind:'briefing_watch',order_id:'ORD-005',status:'pending',
      created_at:'2026-04-01T09:00:00+08:00',observation_day:'2026-04-01',report_day:'2026-04-02'}];
    await page.route('http://localhost:15051/**', async route => {
      const url = new URL(route.request().url());
      if (route.request().method() === 'DELETE') {
        const index=records.findIndex(r=>r.id===url.pathname.split('/').pop());
        assert.notEqual(index,-1);
        records.splice(index,1);
        return route.fulfill({json:{status:'deleted'}});
      }
      if (url.pathname === '/api/v1/management-records/notes') {
        const body = route.request().postDataJSON();
        records.push({...body, id:'note-1', kind:'note', status:'saved', created_at:'2026-04-01T10:00:00+08:00'});
        return route.fulfill({json:{status:'saved'}});
      }
      if (url.pathname === '/api/v1/management-records') {
        const order = url.searchParams.get('order_id');
        return route.fulfill({json:{can_delete:true,records:records.filter(r=>!order || r.order_id === order)}});
      }
      if (url.pathname === '/api/snapshot') return route.fulfill({json:snapshot});
      if (url.pathname === '/api/scheduling/risk') return route.fulfill({json:risk});
      if (url.pathname === '/api/email/clock') return route.fulfill({json:{now:'2026-04-01T10:00:00+08:00',mode:'legacy',version:0}});
      if (url.pathname.startsWith('/api/')) return route.fulfill({json:{}});
      const file = path.join(__dirname,'../../frontend',url.pathname === '/'?'index.html':url.pathname);
      try { return await route.fulfill({path:file}); }
      catch { return route.fulfill({status:404}); }
    });
    await page.goto('http://localhost:15051/#/order?id=ORD-005');
    await page.getByText('Pending check', {exact:false}).waitFor();
    await page.getByRole('button',{name:'Add note'}).click();
    await page.locator('#note-text').fill('Demand changed');
    await page.getByRole('button',{name:'Save note'}).click();
    await page.getByText('Demand changed',{exact:true}).waitFor();
    await page.goto('http://localhost:15051/#/messages');
    await page.getByText('Demand changed',{exact:true}).waitFor();
    await page.reload();
    await page.getByText('Demand changed',{exact:true}).waitFor();
    const removeNote=page.getByRole('button',{name:'Delete Internal note for ORD-005'});
    page.once('dialog',dialog=>dialog.dismiss());
    await removeNote.click();
    await page.getByText('Demand changed',{exact:true}).waitFor();
    page.once('dialog',dialog=>dialog.accept());
    await removeNote.click();
    await removeNote.waitFor({state:'detached'});
    await page.goto('http://localhost:15051/#/order?id=ORD-005');
    const removeWatch=page.getByRole('button',{name:'Delete Morning briefing follow-up for ORD-005'});
    page.once('dialog',dialog=>dialog.accept());
    await removeWatch.click();
    await removeWatch.waitFor({state:'detached'});
    assert.equal(records.length,0);
    await page.goto('http://localhost:15051/#/order?id=ORD-017');
    await page.getByText('No shared records yet.').first().waitFor();
    assert.equal(await page.getByText('Demand changed').count(),0);
    console.log('PASS: order note entry, shared overview, reload and order scope');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
