/* Run against a dedicated test database only (QUEUE_TEST_URL). */
const assert=require('assert/strict'),path=require('path'),fs=require('fs');
const {chromium}=require('playwright');
(async()=>{
 const base=process.env.QUEUE_TEST_URL;
 if(!base)throw new Error('Set QUEUE_TEST_URL to an isolated local test server.');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 const out=path.resolve(__dirname,'../../.build/queue-browser-shots');fs.mkdirSync(out,{recursive:true});
 try{
  const risks=await (await page.request.get(base+'/api/scheduling/risk')).json();
  let candidate;
  for(const o of risks.orders){
   const p=await (await page.request.post(base+'/api/scheduling/orders/'+o.order_id+'/preview')).json();
   if(p.can_apply){candidate=p;break;}
  }
  assert(candidate,'Need a dispatch candidate in the test fixture');
  await page.goto(base+'/#/risk');
  await page.getByRole('heading',{name:'Risk and dispatch decisions'}).waitFor();
  await page.locator('[data-action=risk-select][data-id="'+candidate.order_id+'"]').click();
  await page.getByRole('button',{name:'Analyze expedite impact'}).click();
  const dialog=page.locator('.expedite-dialog');await dialog.waitFor();
  assert((await dialog.innerText()).includes('Affected orders'));
  await page.screenshot({path:path.join(out,'review-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Page overflows on mobile');
  assert(await dialog.evaluate(d=>d.getBoundingClientRect().width<=innerWidth),'Dialog overflows on mobile');
  await page.screenshot({path:path.join(out,'review-mobile.png'),fullPage:true});
  await dialog.locator('[name=reviewer]').fill('Test manager');
  await dialog.locator('[name=note]').fill('Reviewed affected orders in isolated test database.');
  await dialog.locator('[name=token]').fill('queue-test-manager');
  await dialog.locator('[name=reviewed]').check();
  await dialog.getByRole('button',{name:'Approve and adjust schedule'}).click();
  await dialog.getByText('Decision applied. Saved to shared history.',{exact:true}).waitFor();
  assert.equal(await dialog.locator('[name=token]').inputValue(),'');
  await dialog.getByRole('button',{name:'Close',exact:true}).click();
  await page.reload();
  await page.getByRole('heading',{name:'Risk and dispatch decisions'}).waitFor();
  const after=await (await page.request.get(base+'/api/scheduling/risk')).json();
  assert.equal(after.schedule.priority[0],candidate.order_id);
  assert.equal(after.orders.find(o=>o.order_id===candidate.order_id).risk.best_date,candidate.finish_after);
  await page.getByRole('button',{name:'Decision history'}).click();
  await page.getByText('Reviewed affected orders in isolated test database.',{exact:false}).waitFor({state:'attached'});
  assert.deepEqual(errors,[]);
  console.log('PASS: live risk → preview → mobile review → manager apply → persistent schedule → history; no browser errors.');
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});throw e}
 finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
