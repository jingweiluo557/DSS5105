/* Uses an isolated backend with a deterministic model fixture. */
const {chromium}=require('playwright'),assert=require('assert/strict');
(async()=>{
 const base=process.env.QUEUE_TEST_URL;if(!base)throw Error('Set QUEUE_TEST_URL to an isolated test server');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 try{
  const open=async()=>{await page.goto(base+'/#/risk');await page.locator('[data-action=risk-select][data-id="ORD-114"]').click();await page.getByRole('button',{name:'Analyze expedite impact'}).click();await page.locator('.expedite-dialog').waitFor()};
  await open();let dialog=page.locator('.expedite-dialog');
  await dialog.locator('[name=reviewer]').fill('Draft reviewer');
  await dialog.locator('[name=decision]').selectOption('reject');
  await dialog.locator('[name=note]').fill('My manual reason must survive.');
  await dialog.locator('[data-draft-generate]').click();
  await page.waitForFunction(()=>document.querySelector('[data-draft-candidate]').textContent.includes('ORD-114'));
  assert.equal(await dialog.locator('[name=note]').inputValue(),'My manual reason must survive.');
  const first=await dialog.locator('[data-draft-candidate]').textContent();
  await dialog.locator('[name=draft_instruction]').fill('再短一点');
  await dialog.locator('[data-draft-generate]').click();
  await page.waitForFunction(first=>document.querySelector('[data-draft-candidate]').textContent!==first,first);
  const revised=await dialog.locator('[data-draft-candidate]').textContent();
  assert.equal(await dialog.locator('[name=note]').inputValue(),'My manual reason must survive.');
  await page.reload();await page.locator('[data-action=risk-select][data-id="ORD-114"]').click();await page.getByRole('button',{name:'Analyze expedite impact'}).click();dialog=page.locator('.expedite-dialog');
  await dialog.waitFor();assert.equal(await dialog.locator('[name=note]').inputValue(),'My manual reason must survive.');
  assert.equal(await dialog.locator('[data-draft-candidate]').textContent(),revised);
  await dialog.locator('[data-draft-adopt]').click();
  await page.waitForFunction(revised=>document.querySelector('[name=note]').value===revised,revised);
  assert(!await dialog.locator('[name=reviewed]').isChecked());
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:'.build/review-draft-mobile.png',fullPage:true});
  await dialog.locator('[name=reviewed]').check();await dialog.getByRole('button',{name:'Reject',exact:true}).click();
  await dialog.getByText('Decision rejected. Saved to shared history.',{exact:true}).waitFor();
  const history=await (await page.request.get(base+'/api/scheduling/history')).json();
  assert(history.some(r=>r.order_id==='ORD-114'&&r.note===revised&&r.status==='rejected'));
  const queue=await (await page.request.get(base+'/api/scheduling/risk')).json();assert.deepEqual(queue.schedule.priority,[]);
  assert.deepEqual(errors,[]);
  console.log('PASS: AI drafting/revision, manual edit protection, reload recovery, adoption, mobile, final reviewed submission.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
