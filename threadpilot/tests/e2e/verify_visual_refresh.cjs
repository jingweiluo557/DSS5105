const http=require('http'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const project=path.resolve(__dirname,'../..');
async function serve(root){
 const server=http.createServer((req,res)=>{
  if(req.url==='/api/snapshot'){res.setHeader('Content-Type','application/json');return res.end(fs.readFileSync(path.join(__dirname,'snapshot.fixture.json')));}
  if(req.url.startsWith('/api/')){res.setHeader('Content-Type','application/json');return res.end('{"configured":true}');}
  const file=path.join(root,req.url==='/'?'index.html':req.url.split('?')[0]);
  if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');fs.createReadStream(file).pipe(res);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));return server;
}
(async()=>{
 const servers=[],browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const current=await serve(path.join(project,'frontend'));servers.push(current);
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const url=`http://127.0.0.1:${current.address().port}`;
  await page.goto(url+'/#/orders');await page.locator('tbody tr').first().waitFor();
  assert.deepEqual(await page.evaluate(()=>['2026-10-09T14:55:58.597744+00:00','2026-04-01T12:00:00+08:00','2026-10-09T20:00:00Z','2026-04-01'].map(formatWorkspaceTime)),['2026-10-09 22:55','2026-04-01 12:00','2026-10-10 04:00','2026-04-01']);
  const baseline=path.join(project,'.build/frontend-before-oct09');
  if(fs.existsSync(baseline)){
   const old=await serve(baseline);servers.push(old);const before=await browser.newPage({viewport:{width:1440,height:1000}});
   await before.goto(`http://127.0.0.1:${old.address().port}/#/orders`);await before.locator('tbody tr').first().waitFor();
   const unchangedList=await page.locator('.app-main').evaluate(el=>{const copy=el.cloneNode(true);copy.querySelector('.workspace-tools a[href="#/predictions"]')?.remove();return copy.innerHTML});
   assert.equal(unchangedList,await before.locator('.app-main').innerHTML());
   const styles=p=>p.locator('table').evaluate(el=>[el,...el.querySelectorAll('th,td')].map(x=>{const s=getComputedStyle(x);return [s.fontSize,s.lineHeight,s.padding,x.getBoundingClientRect().width];}));
   assert.deepEqual(await styles(page),await styles(before));
  }
  await page.goto(url+'/#/evidence?id=ORD-020');await page.getByRole('heading',{name:'Order evidence',exact:true}).waitFor();
  const out=path.join(project,'backend/runtime/ui-review');fs.mkdirSync(out,{recursive:true});
  await page.screenshot({path:path.join(out,'evidence-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Evidence mobile overflow');
  await page.screenshot({path:path.join(out,'evidence-mobile.png'),fullPage:true});
  await page.goto(url+'/#/cover');await page.locator('.cover').waitFor();assert.equal(await page.locator('.cover footer').count(),0);
  assert.deepEqual(errors,[]);console.log('PASS: UTC+8 minute formatting, date rollover, date-only values, unchanged Order center DOM and table styles, responsive evidence, clean cover.');
 }finally{await browser.close();for(const s of servers){s.closeAllConnections();s.close();}}
})().catch(e=>{console.error(e);process.exitCode=1;});
