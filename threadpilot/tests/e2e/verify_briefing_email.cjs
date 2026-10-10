const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs'),path=require('path');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/#/dashboard');
 await page.locator('[data-action="briefing-email"]').waitFor();await page.locator('[data-action="briefing-email"]').click();
 const dialog=page.locator('#briefing-email-dialog');await dialog.waitFor();
 assert((await dialog.locator('[name=body]').inputValue()).includes('2026-04-01'));
 const out=path.resolve(__dirname,'../../backend/runtime/ui-review');
 await page.screenshot({path:path.join(out,'briefing-email-desktop.png')});
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(out,'briefing-email-mobile.png')});
 await dialog.locator('.email-close').click();await page.locator('[data-action="briefing-email"]').click();await dialog.waitFor();
 // Isolate UI edit/conflict scenarios from the real shared draft.
 let saved={subject:'Edited subject',body:'Edited <message> & follow-up',version:2,updated_at:'2026-10-10T12:00:00+08:00'},fail=false;
 await page.route('**/api/dashboard/briefings/*/email',async route=>{
  const req=route.request();if(req.method()==='PUT'){if(fail)return route.fulfill({status:409,json:{}});saved={...saved,...req.postDataJSON(),version:saved.version+1}}
  await route.fulfill({json:saved});
 });
 await dialog.locator('[name=subject]').fill(saved.subject);await dialog.locator('[name=body]').fill(saved.body);
 await dialog.getByText('Save draft',{exact:true}).click();await page.waitForFunction(()=>document.querySelector('.email-status').textContent.startsWith('Saved'));
 await dialog.locator('.email-close').click();await page.locator('[data-action="briefing-email"]').click();await dialog.waitFor();assert.equal(await dialog.locator('[name=body]').inputValue(),saved.body);
 const pending=page.waitForEvent('download');await dialog.locator('.email-download').click();const download=await pending;const target=path.join(out,'briefing-email-test.eml');await download.saveAs(target);
 const raw=fs.readFileSync(target,'utf8');assert(raw.includes('X-Unsent: 1'));assert(Buffer.from(raw.split('\r\n\r\n')[1].replace(/\s/g,''),'base64').toString('utf8').includes('Edited <message>'));
 fail=true;await dialog.locator('[name=body]').fill('Keep my unsaved changes');await dialog.getByText('Save draft',{exact:true}).click();await page.getByText(/Your edits are still here/).waitFor();assert.equal(await dialog.locator('[name=body]').inputValue(),'Keep my unsaved changes');
 assert.deepEqual(errors,[]);console.log('PASS: real cloud draft creation/reopen, desktop/mobile, isolated edit/reopen, EML encoding, conflict preserves edits.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
