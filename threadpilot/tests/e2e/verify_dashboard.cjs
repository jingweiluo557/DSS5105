const http=require('http'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../../frontend');
const snapshot=JSON.parse(fs.readFileSync(path.join(__dirname,'snapshot.fixture.json'),'utf8'));
const report={day:'2026-10-10',business_date:'2026-04-01',generated_at:'2026-10-10T07:00:00+08:00',yesterday:'2,567 stage completions across four stages.',top_issue:'ORD-107 requires review.',decide:'8 overdue.',production_note:'Assembly below baseline.',cleared:[]};
const counts={in_progress:34,overdue:8,due_today:1,idle:2,priority:2};
const data={business_date:'2026-04-01',counts,health:{on_track:17,at_risk:9,late:8,basis:'Imported delay model ≥60%',delivery:{rate:57.1,on_time:20,total:35},prior_delivery:{rate:61.4,on_time:27,total:44}},
 tasks:[{id:'auto:ORD-107',order_id:'ORD-107',title:'ORD-107 · Northwind Apparel',origin:'auto',done:false,version:1,reasons:['Overdue']}],
 orders:[{order_id:'ORD-107',due_days:-16,score:57}],history:[{date:'2026-03-31',...counts,overdue:7},{date:'2026-04-01',...counts}],briefings:[report],
 advice:[{title:'Review predicted delivery risk',text:'Verify progress before promising delivery.',orders:['ORD-107']}],forecast:{available:true}};
(async()=>{
 let failWrite=false;
 const server=http.createServer((req,res)=>{
  res.setHeader('Content-Type','application/json');
  if(req.url==='/api/snapshot')return res.end(JSON.stringify(snapshot));
  if(req.url==='/api/dashboard')return res.end(JSON.stringify(data));
  if(req.url.startsWith('/api/dashboard/tasks')){
   let raw='';req.on('data',c=>raw+=c);req.on('end',()=>{
    if(failWrite){res.writeHead(503);return res.end('{}');}
    const body=JSON.parse(raw);
    if(req.method==='POST'){data.tasks.push({id:'manual:'+body.id,title:body.title,origin:'manual',done:false,version:1,reasons:[]});res.writeHead(201);return res.end(JSON.stringify({id:'manual:'+body.id}));}
    const task=data.tasks.find(t=>t.id===decodeURIComponent(req.url.split('/').at(-1)));assert.equal(body.version,task.version);task.done=body.done;task.version++;res.end('{"status":"saved"}');
   });return;
  }
  if(req.url.startsWith('/api/'))return res.end('{"configured":true}');
  const file=path.join(root,req.url==='/'?'index.html':req.url.split('?')[0]);
  if(!file.startsWith(root)||!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream');fs.createReadStream(file).pipe(res);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/#/dashboard`);
  await page.locator('.todo-item').first().waitFor();assert.equal(await page.locator('.metric-spark').count(),5);
  assert.equal(await page.getByText('Generated 2026-10-10 07:00 · Business date 2026-04-01',{exact:true}).count(),1);
  const input=page.locator('#new-dashboard-task');await input.fill('Review <forecast> & capacity');await page.locator('#dashboard-task-form button').click();
  await page.getByText('Review <forecast> & capacity',{exact:true}).waitFor();
  await page.locator('[data-task-id="auto:ORD-107"]').check();await page.waitForFunction(()=>!document.querySelector('[data-task-id="auto:ORD-107"]'));
  await page.locator('[data-action=dash-filter][data-value=done]').click();assert(await page.locator('[data-task-id="auto:ORD-107"]').isChecked());
  await page.reload();await page.locator('.todo-item').first().waitFor();await page.locator('[data-action=dash-filter][data-value=done]').click();assert(await page.locator('[data-task-id="auto:ORD-107"]').isChecked());
  await page.locator('[data-task-id="auto:ORD-107"]').uncheck();await page.locator('[data-action=dash-filter][data-value=pending]').click();await page.locator('[data-task-id="auto:ORD-107"]').waitFor();
  failWrite=true;await page.locator('[data-task-id="auto:ORD-107"]').check();await page.getByText('Unable to save or load dashboard data. Please retry.',{exact:true}).waitFor();assert(!await page.locator('[data-task-id="auto:ORD-107"]').isChecked());failWrite=false;
  const out=path.resolve(__dirname,'../../backend/runtime/ui-review');fs.mkdirSync(out,{recursive:true});
  if(process.env.DASHBOARD_LIVE_URL){await page.goto(process.env.DASHBOARD_LIVE_URL);await page.locator('.todo-item').first().waitFor();await page.locator('.health-counts').waitFor();}
  await page.screenshot({path:path.join(out,'dashboard-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile overflow');
  await page.screenshot({path:path.join(out,'dashboard-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
  console.log('PASS: KPI sparklines, archived briefing time, manual task escaping, handle/undo, reload persistence, failed-save rollback, desktop/mobile layout.');
 }finally{await browser.close();server.closeAllConnections();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
