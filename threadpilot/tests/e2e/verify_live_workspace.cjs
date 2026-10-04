/* Opt-in integration test: real configured API/MySQL; no intercepted network requests.
 * Creates chat sessions and action previews only. Never confirms business writes. */
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const assert=require('assert/strict');
const base=process.env.LIVE_BASE_URL||'http://127.0.0.1:8000';
const output=path.resolve(__dirname,'../../backend/runtime/live-workspace');
fs.mkdirSync(output,{recursive:true});
const report={started_at:new Date().toISOString(),base,mode:'real API and database; no mocks',turns:[],checks:[],errors:[]};
const save=()=>fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:1000}});
 await page.addInitScript(()=>{
  window.liveResponses=[];
  const originalFetch=window.fetch;
  window.fetch=async(...args)=>{
   const response=await originalFetch(...args);
   if(String(args[0]).endsWith('/api/v1/workflow/chat/stream')) {
    const copy=response.clone();
    copy.text().then(raw=>window.liveResponses.push({raw,status:response.status,input:JSON.parse(args[1].body)}));
   }
   return response;
  };
 });
 page.setDefaultTimeout(100000);
 page.on('pageerror',e=>report.errors.push(e.message));
 try{
  const health=await (await page.request.get(base+'/api/v1/health')).json();
  assert(health.configured,'Model is not configured');report.health=health;
  const snapshot=await (await page.request.get(base+'/api/snapshot')).json();
  report.snapshot={today:snapshot.today,generated_at:snapshot.generated_at,orders:snapshot.orders.length,production:snapshot.production_log.length,workshops:snapshot.workshops.length,latest_production:snapshot.production_log.at(-1).date};
  await page.goto(base+'/#/ai');await page.locator('.copilot-workspace').waitFor();
  async function turn(question,button){
   const before=report.turns.length;
   const captured=await page.evaluate(()=>window.liveResponses.length);
   if(button)await page.getByRole('button',{name:button,exact:true}).click();
   else{await page.locator('[name=visible-question]').fill(question);await page.locator('[data-form=chat] [type=submit]').click();}
   await page.waitForFunction(n=>window.liveResponses.length>n,captured);
   const response=await page.evaluate(()=>window.liveResponses.at(-1));const raw=response.raw;
   const frames=raw.split(/\r?\n\r?\n/).map(frame=>({event:frame.match(/^event: (.*)/m)?.[1],data:frame.match(/^data: (.*)/m)?.[1]}));
   const done=frames.find(f=>f.event==='done');
   const result=done?JSON.parse(done.data):null;
   const item={input:response.input,status:response.status,result,error:done?null:raw};
   report.turns.push(item);save();
   console.log(JSON.stringify({turn:before+1,status:item.status,intent:result?.intent,answer:result?.answer,error:item.error}));
   assert.equal(item.status,200);assert(result?.answer);
   await page.waitForFunction(()=>!aiBusy);
   for(const e of result.evidence||[]){
    const res=await page.request.get(base+e.url);assert.equal(res.status(),200);
    const actual=await res.json();assert.equal(actual.record_id||actual.id,e.record_id||e.row);
    for(const [key,value] of Object.entries(e.record||{}))assert.equal(String(actual.record[key]??''),String(value??''),`Evidence mismatch: ${key}`);
   }
   item.evidence_verified=(result.evidence||[]).length;save();return result;
  }
  const lookup=await turn('Open order ORD-005 and show its latest stage and activity.');
  const refresh=await turn('Refresh it now. What is its current stage and last activity date?');
  assert.equal(report.turns[1].input.session_id,lookup.state.session_id);
  assert.equal(refresh.state.active_order,'ORD-005');report.checks.push('Multi-turn order context retained');
  assert(lookup.evidence.length>0);report.checks.push('Every returned evidence link matches current database fields');
  await page.getByRole('button',{name:'New conversation',exact:true}).click();
  const brief=await turn(null,'Generate daily report ↗');
  if(brief.needs_clarification)await turn('Today only.');
  await page.screenshot({path:path.join(output,'daily-report.png'),fullPage:true});
  await turn('How was assembly output yesterday?');
  await turn('Use March 31, 2026 for assembly output and compare with the same-weekday baseline.');
  await page.getByRole('button',{name:'New conversation',exact:true}).click();
  const note=await turn('Draft an internal decision note for ORD-005: Integration check only; await manager review. Do not save it yet.');
  report.checks.push('Internal note preview requested without confirmation');
  report.preview_confirmation_present=Boolean(note.confirmation_id);
  assert(note.confirmation_required && note.confirmation_id,'Expected a confirmation preview');
  const notifications=await page.request.get(base+'/api/v1/workflow/notifications/'+note.state.session_id);
  assert.equal(notifications.status(),200);report.checks.push('Real session notification endpoint accessible');
  await page.screenshot({path:path.join(output,'action-preview.png'),fullPage:true});
  await page.reload();await page.locator('.copilot-workspace').waitFor();
  assert.equal(await page.evaluate(()=>workflowSession),note.state.session_id);report.checks.push('Session survives reload');
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('.sidebar').getBoundingClientRect().right<=0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
  report.checks.push('Mobile layout has no horizontal overflow');
  await page.setViewportSize({width:1600,height:1000});
  await page.goto(base+'/#/dashboard');await page.locator('.kpis').waitFor();
  assert((await page.locator('.page-head').innerText()).includes(snapshot.today));
  await page.screenshot({path:path.join(output,'dashboard.png'),fullPage:true});
  report.checks.push('Dashboard displays the backend business date');
  assert.deepEqual(report.errors,[]);
  report.passed=true;
 }catch(error){report.failure=error.message;throw error;}
 finally{report.finished_at=new Date().toISOString();save();await browser.close();console.log('Report: '+path.join(output,'report.json'));}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
