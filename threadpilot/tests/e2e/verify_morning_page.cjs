/* Read-only page check; real-model order conversation requires MORNING_LIVE_CHAT=1. */
const {chromium}=require('playwright'),assert=require('assert/strict');
(async()=>{
 const base=process.env.MORNING_TEST_URL;if(!base)throw Error('Set MORNING_TEST_URL');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],apis=[];
 page.setDefaultTimeout(120000);page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/'))apis.push(r.url())});
 try{
  await page.goto(base+'/demo/briefing_demo.html');await page.locator('#report .brief-grid').waitFor();
  assert.equal(new URL(page.url()).pathname,'/briefing.html');
  assert((await page.locator('#connection').innerText()).includes(base));
  assert((await page.locator('#report').innerText()).includes('gpt-4.1'));
  await page.locator('#report details').first().locator('summary').click();
  await page.screenshot({path:'.build/morning-desktop.png',fullPage:true});
  if(process.env.MORNING_LIVE_CHAT==='1'){
   for(const question of ['ORD-114 是否值得插队？','它会影响谁？']){
    const count=await page.locator('#chat-log p').count();await page.locator('#question').fill(question);
    await page.locator('#chat-form button').click();await page.waitForFunction(n=>document.querySelectorAll('#chat-log p').length>n,count);
   }
   const last=await page.locator('#chat-log p').last().innerText();assert(last.includes('ORD-114'));assert(last.includes('Affected orders:'));
  }
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile overflow');
  await page.screenshot({path:'.build/morning-mobile.png',fullPage:true});
  assert(apis.every(u=>new URL(u).origin===base),'Unexpected backend origin');assert.deepEqual(errors,[]);
  console.log('PASS: legacy demo URL, current report/evidence, desktop/mobile layout, same LAN backend'+(process.env.MORNING_LIVE_CHAT==='1'?', real two-turn order chat':'')+'.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
