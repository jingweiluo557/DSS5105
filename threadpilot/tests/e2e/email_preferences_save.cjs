const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
 const listeners={},root={isConnected:true},status={},queue=[],writes=[];
 let fail=false,prefs={version:0,manager_email:'manager@example.com',manager_name:'Manager',subject_prefix:'Morning',briefing_enabled:false,customers:[],departments:{KNITTING:'floor@example.com'}};
 const ctx={document:{addEventListener:(k,f)=>listeners[k]=f,getElementById:id=>id==='email-settings-content'?root:status},setInterval(){},queueMicrotask:f=>queue.push(f),head:()=>'',btn:()=>'',esc:String,state:{settings:{idle:2},audit:[]},render(){},toast(){},window:{THREADPILOT_API_BASE:'https://example.test',threadpilotFetch:async(url,opts)=>{
 if(opts.method==='PUT'){writes.push(JSON.parse(opts.body));if(fail)return{ok:false,status:409,json:async()=>({detail:'Version changed'})};prefs={...writes.at(-1),version:prefs.version+1,start_day:'2026-03-29',clock_run_id:'run'};return{ok:true,json:async()=>({preferences:prefs})};}
 return{ok:true,json:async()=>({preferences:prefs,connection:{connected:true},clock:{now:'2026-03-28T07:05:00+08:00',run_id:'run',schedule_start_day:'2026-03-28'}})};
 }},FormData:class{constructor(f){this.f=f;}get(n){return this.f.values[n]||'';}has(n){return this.f.elements[n]?.checked||false;}}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('frontend/email-settings.js','utf8'),ctx);ctx.settingsPage();await queue.shift()();
 let valid=true,submission;const button={},toggle={name:'briefing_enabled',checked:true};const form={id:'email-preferences',elements:{briefing_enabled:toggle},values:{manager_email:'manager@example.com',manager_name:'Manager',subject_prefix:'Morning',department_KNITTING:'floor@example.com'},querySelector:()=>button,querySelectorAll:()=>[],reportValidity:()=>valid,requestSubmit:()=>{submission=listeners.submit({target:form,preventDefault(){}});}};toggle.form=form;
 listeners.change({target:toggle});await submission;
 assert.equal(writes.length,1);assert.equal(prefs.briefing_enabled,true);assert.equal(prefs.departments.KNITTING,'floor@example.com');assert.match(root.innerHTML,/Scheduled from 2026-03-29/);
 fail=true;toggle.checked=false;listeners.change({target:toggle});await submission;assert.equal(toggle.checked,true);assert.match(status.textContent,/not saved/);assert.equal(toggle.disabled,false);
 valid=false;toggle.checked=false;listeners.change({target:toggle});assert.equal(toggle.checked,true);assert.equal(writes.length,2);
 console.log('PASS: checkbox persists, fields preserved, effective start date, failed save rollback, invalid form blocked');
})().catch(e=>{console.error(e);process.exitCode=1});
