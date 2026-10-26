// Read-only check against a running backend with the imported prediction batch.
const {chromium}=require('playwright'),assert=require('assert/strict'),path=require('path'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto((process.env.PREDICTION_PREVIEW_URL||'http://127.0.0.1:8000')+'/#/predictions');
  await page.locator('.prediction-table tbody tr').first().waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('.prediction-table tbody tr').length===15);
  assert.equal(await page.locator('.workspace-tools a[href="#/orders"] + a').getAttribute('href'),'#/predictions');
  await page.locator('[data-action=prediction-next]').click();assert.equal(await page.locator('.prediction-table tbody tr').count(),15);
  await page.locator('[data-action=prediction-next]').click();assert.equal(await page.locator('.prediction-table tbody tr').count(),4);
  await page.locator('#prediction-filters [name=query]').fill('ORD-107');assert.equal(await page.locator('.prediction-table tbody tr').count(),1);
  await page.locator('[data-action=prediction-detail]').click();await page.getByRole('dialog',{name:'ORD-107 · Forecast'}).waitFor();
  assert.equal(await page.getByText('99.3% delay risk',{exact:true}).count(),1);
  await page.getByRole('link',{name:'View source data',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.record-dialog pre')?.textContent.includes('LogisticRegression'));
  await page.getByRole('button',{name:'Close record'}).click();await page.getByRole('button',{name:'Done',exact:true}).click();
  await page.locator('[data-action=prediction-clear]').click();await page.locator('#prediction-filters [name=risk]').selectOption('LOW');assert.equal(await page.locator('.prediction-table tbody tr').count(),14);
  await page.locator('[data-action=prediction-clear]').click();
  const out=path.resolve(__dirname,'../../backend/runtime/ui-review');fs.mkdirSync(out,{recursive:true});await page.screenshot({path:path.join(out,'predictions-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Prediction mobile overflow');
  await page.screenshot({path:path.join(out,'predictions-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
  console.log('PASS: live 34 database forecasts, navigation placement, pagination, risk/search filters, forecast details, authenticated sources, mobile table scrolling.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
