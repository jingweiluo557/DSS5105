/* The GM home screen (docs/CEO_INTERFACE_REVIEW.md): one status line, the decisions only the manager can make, one
   picture of order health, one of production, the chat box. Everything else is one tap away. The payload comes from
   GET /api/dashboard/home (same snapshot and detectors as the chat tools and the alert policy); the saved AI briefing
   and the manager's own to-dos come from GET /api/dashboard. Nothing regenerates on page load. */
let dashboardData=null,dashboardError='',dashboardLoading=false,morningLoading=false,morningError='',morningReport=null,homeData=null,homeError='';
const STAGE_SHORT={KNITTING:'Knit',ASSEMBLY:'Asm',WASHING:'Wash',PACKING:'Pack'};
function homeFallback(){
 // Older backend without /api/dashboard/home: the same screen from what the page already loaded, without the alert policy.
 const late=overdue.length,risky=activeOrders.filter(o=>!overdue.includes(o)&&['high','medium'].includes(window.QUEUE_DATA?.orders.find(x=>x.order_id===o.id)?.risk.level)).length;
 const cards=[...overdue].sort((a,b)=>a.due.localeCompare(b.due)).slice(0,3).map(o=>({key:'overdue:'+o.id,tier:'P2',kind:'overdue',entity:o.id,title:`${o.id} is ${-o.daysToDue} day${-o.daysToDue===1?'':'s'} late`,lines:[`${o.customer}, ${o.qty.toLocaleString()} ${o.product}, still at ${o.stage.toLowerCase()}`],action:{label:'Confirm a new date',kind:'route',value:'risk?id='+o.id}}));
 const pulse=stageStats.map(s=>({stage:s.stage,date:s.latest.date,pieces:s.latest.pieces_completed,band:null,status:s.change<-20?'below':'within',change_pct:Math.round(s.change),below_days:0}));
 const worst=pulse.find(p=>p.status==='below');
 return {business_date:TODAY,status:{colour:late?'amber':'green',label:late?'AMBER':'GREEN',date_label:new Date(TODAY+'T12:00:00Z').toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'short',timeZone:'UTC'}),facts:[`${late} overdue`,...(worst?[`${titleCase(worst.stage)} ${worst.change_pct}% yesterday`]:[]),cards.length?`${cards.length} decision${cards.length===1?'':'s'} need you`:'no decisions waiting'],meaning:'Alert tiers need the updated backend; showing overdue orders only.'},decisions:cards,more_waiting:Math.max(0,late-cards.length),counts:{in_progress:activeOrders.length,overdue:late,due_today:dueToday.length,idle:idleOrders.length,total:orders.length},health:{late,at_risk:risky,on_track:activeOrders.length-late-risky,unknown:0,active:activeOrders.length,on_time_rate:null,on_time_basis:'',on_time_change_pts:null},pulse,alerts:{P1:0,P2:late,P3:0},fallback:true};
}
function statusLine(){
 const h=homeData||homeFallback(),s=h.status;
 return `<section class="status-line ${s.colour}" aria-label="Factory status"><div class="status-main"><span class="status-dot" aria-hidden="true"></span><div><strong>${esc(s.date_label)} · ${esc(s.label)}</strong><span class="status-facts">${s.facts.map(f=>esc(f)).join(' <i>·</i> ')}</span></div></div><div class="status-side"><small class="muted">${esc(s.meaning)}</small>${btn('dash-refresh',dashboardLoading?'Refreshing…':'Refresh','small-button',dashboardLoading?'disabled':'')}</div></section>`;
}
function kpiStrip(){
 const h=homeData||homeFallback(),c=h.counts,he=h.health;
 const items=[[c.in_progress,'in progress','orders?status=In%20progress'],[c.overdue,'overdue','orders?due=Overdue'],[c.due_today,'due today','orders?due=Today'],[c.idle,'idle ≥5 days','orders?idle=5'],[he.at_risk,'at risk','risk'],[he.on_time_rate===null?'—':he.on_time_rate+'%','on time, 30 days'+(he.on_time_change_pts===null?'':` (${he.on_time_change_pts>=0?'+':''}${he.on_time_change_pts} pts)`),'orders?status=Complete']];
 return `<nav class="kpi-strip" aria-label="Counts">${items.map(([n,label,url])=>`<a href="#/${url}"><strong>${esc(String(n))}</strong> ${esc(label)}</a>`).join('')}</nav>`;
}
function decisionCards(){
 const h=homeData||homeFallback();
 const cards=h.decisions.map(c=>`<article class="decision ${c.tier==='P1'?'p1':'p2'}" data-key="${esc(c.key)}"><div class="decision-head"><span class="badge ${c.tier==='P1'?'severe':'warning'}">${c.tier==='P1'?'Act now':'Decide today'}</span>${c.entity&&find(c.entity)?link('order','Open',c.entity,'small-link'):''}</div><h3>${esc(c.title)}</h3>${(c.lines||[]).map(l=>`<p>${esc(l)}</p>`).join('')}<div class="actions">${c.action.kind==='chat'?btn('decide-chat',esc(c.action.label),'primary',`data-message="${esc(c.action.message)}"`):btn('decide-route',esc(c.action.label),'primary',`data-route="${esc(c.action.value)}"`)}${c.options?`<small class="muted">${esc(c.options.join(' · '))}</small>`:''}</div></article>`).join('');
 const empty=`<article class="decision none"><h3>Nothing needs a decision today.</h3><p>The briefing has the detail; the counters below say where to look.</p></article>`;
 return `<section class="decide" aria-label="Decide today"><div class="section-heading"><div class="eyebrow">DECIDE TODAY</div>${h.more_waiting?`<a href="#/risk" class="small-link">${h.more_waiting} more in Risk orders →</a>`:''}</div><div class="decision-cards">${cards||empty}</div></section>`;
}
function healthCard(){
 const h=(homeData||homeFallback()).health,total=h.active||1;
 const seg=[['late',h.late],['at-risk',h.at_risk],['on-track',h.on_track],['unknown',h.unknown||0]];
 return `<section class="card home-health"><div class="section-heading"><h2>Order health</h2><small>${h.active} in progress</small></div><div class="health-bar" role="img" aria-label="${h.late} late, ${h.at_risk} at risk, ${h.on_track} on track">${seg.map(([c,n])=>`<span class="${c}" style="width:${n/total*100}%"></span>`).join('')}</div><p class="health-line"><span><i class="late"></i>${h.late} late</span><span><i class="at-risk"></i>${h.at_risk} at risk</span><span><i class="on-track"></i>${h.on_track} on track</span>${h.unknown?`<span><i class="unknown"></i>${h.unknown} unassessed</span>`:''}</p>${h.on_time_rate===null?'':`<p class="muted">On time ${h.on_time_rate}% of completed orders in the last 30 days${h.on_time_change_pts===null?'':` (${h.on_time_change_pts>=0?'+':''}${h.on_time_change_pts} pts vs the 30 before)`}.</p>`}<div class="actions">${link('risk','Review the list →','','small-link')}</div></section>`;
}
function pulseCard(){
 const rows=(homeData||homeFallback()).pulse;
 const top=Math.max(...rows.map(r=>Math.max(r.pieces||0,r.band?.max||0)))*1.08||1,pct=v=>Math.max(0,Math.min(100,v/top*100));
 const cols=rows.map(r=>{const pieces=r.pieces||0,cls=r.status==='below'?'below':r.status==='above'?'above':'within';
  return `<a class="pulse-col" href="#/exceptions" aria-label="${r.stage} ${pieces} pieces on ${r.date||'no record'}, ${cls} its normal range"><div class="pulse-plot">${r.band?`<i class="band" style="bottom:${pct(r.band.min)}%;height:${Math.max(1.5,pct(r.band.max)-pct(r.band.min))}%"></i>`:''}<b class="pbar ${cls}" style="height:${pct(pieces)}%"><span class="value">${pieces.toLocaleString()}</span></b></div><span class="label">${titleCase(r.stage)}</span>${r.status==='below'&&r.change_pct!==null?`<span class="delta">${r.change_pct}%${r.below_days>=2?` · ${r.below_days} d`:''}</span>`:'<span class="delta ok">in range</span>'}</a>`}).join('');
 const latest=rows.find(r=>r.date)?.date;
 const worst=rows.filter(r=>r.status==='below').sort((a,b)=>(a.change_pct??0)-(b.change_pct??0))[0];
 return `<section class="card home-pulse"><div class="section-heading"><h2>Production pulse</h2><small>${latest?date(latest):'no record'}</small></div><div class="pulse-chart" role="img" aria-label="Latest working-day output per stage against its normal range">${cols}</div><p class="muted">${worst?`${titleCase(worst.stage)} is ${Math.abs(worst.change_pct)}% under its normal range${worst.below_days>=2?` and has been for ${worst.below_days} working days`:''}.`:'Every stage is inside its normal range.'} The shaded band is the previous eight same-weekday records.</p><details class="why-eight"><summary>Why eight same weekdays?</summary><p class="muted">The factory is closed on Sundays and each weekday runs at its own level, so a day is compared with the same weekday. Measured on this factory's data, 8 weeks (about two months) cut false alerts from about 0.67 a month with 4 weeks to about 0.1, and still catch every 30% drop on its third day; 10 to 12 weeks add little and need more history than the 90 days hold. Ask “why eight?” in the chat for the numbers.</p></details></section>`;
}
function firstPoint(text){const p=String(text||'').split(/\r?\n/).map(l=>l.replace(/^\s*[-*•]\s*/,'').trim()).filter(Boolean);const first=p[0]||'';const m=first.match(/^.{20,}?[.!?](?=\s|$)/);return m?m[0]:first}
function briefingCard(){
 const report=morningReport||dashboardData?.ai_briefing||null;
 const rows=report?[['Production',report.yesterday],['Priorities',report.top_issue],['Next steps',report.decide]].filter(([,t])=>t):[];
 return `<section class="card home-briefing"><div class="section-heading"><h2>Morning briefing</h2><small>${report?.generated_at?'written '+formatWorkspaceTime(report.generated_at):morningLoading?'writing…':'not written yet'}</small></div>${morningError?`<p class="callout error" role="alert">${esc(morningError)}</p>`:''}${rows.length?`<dl class="brief-rows">${rows.map(([k,t])=>`<div><dt>${k}</dt><dd>${esc(firstPoint(t))}</dd></div>`).join('')}</dl>`:`<p class="muted">${morningLoading?'The model is reading the records…':dashboardLoading?'Loading…':'No AI briefing has been written for this business date.'}</p>`}<div class="actions"><a class="button small-button" href="briefing.html">Open the full briefing</a>${btn('dash-analyze',morningLoading?'Writing…':report?'Rewrite':'Write it now','small-button',morningLoading?'disabled':'')}${report?btn('dash-brief-chase','Draft chase-up','small-button'):''}</div></section>`;
}
function todosCard(){
 const all=dashboardData?.tasks||[],manual=all.filter(t=>t.origin==='manual'&&!t.done),ai=all.filter(t=>t.origin==='ai'&&!t.done&&/ORD-\d+|knitting|assembly|washing|packing/i.test(t.title)&&!/^(verify|check|confirm whether)/i.test(t.title)).slice(0,3),done=all.filter(t=>t.done).length;
 const item=t=>`<li class="todo-item"><label class="todo-check"><input type="checkbox" data-task-id="${esc(t.id)}" aria-label="Mark ${esc(t.title)} handled"></label><span class="todo-text" title="${esc(t.title)}">${esc(t.title.length>110?t.title.slice(0,107)+'…':t.title)}</span>${t.order_id&&find(t.order_id)?link('order','Open',t.order_id,'small-link'):t.origin==='ai'?btn('dash-task-chase','Draft','small-link',`data-task="${esc(t.id)}"`):''}</li>`;
 return `<section class="card home-todos"><div class="section-heading"><h2>Your to-dos</h2><small>${manual.length+ai.length} open${done?` · ${done} handled`:''}</small></div><ul class="todo-list">${[...manual,...ai].map(item).join('')||'<li class="muted">Nothing on your list.</li>'}</ul><form id="dashboard-task-form"><label class="screenreader" for="new-dashboard-task">Add a to-do</label><div class="todo-input"><input id="new-dashboard-task" name="title" required maxlength="300" placeholder="Add a to-do" ${!dashboardData?'disabled':''}><button type="submit" ${!dashboardData?'disabled':''}>Add</button></div></form></section>`;
}
function askCard(){
 const chips=['Which orders are most at risk?','Did anything go wrong yesterday?','Can we take 800 hoodies by the 25th?'];
 return `<section class="card home-ask" aria-label="Ask ThreadPilot"><div class="section-heading"><h2>Ask ThreadPilot</h2><small>typed or spoken</small></div>${composer().replace('<form class="composer"','<form class="composer home-composer" data-home="1"')}<div class="workspace-suggestions">${chips.map(q=>btn('dash-suggest',esc(q),'small-button',`data-question="${esc(q)}"`)).join('')}</div></section>`;
}
dashboard=function(){return `<div class="dashboard-refresh home">${statusLine()}${dashboardError||homeError?`<div class="callout error" role="alert">${esc(homeError||dashboardError)} ${btn('dash-refresh','Retry','small-button')}</div>`:''}${kpiStrip()}${decisionCards()}<div class="grid two home-row">${healthCard()}${pulseCard()}</div><div class="grid two home-row">${briefingCard()}${todosCard()}</div>${askCard()}</div>`};
async function dashboardRequest(path,options={}){
 const response=await window.threadpilotFetch(window.THREADPILOT_API_BASE+'/api/'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
 if(!response.ok)throw Object.assign(new Error(response.status===409?'This item changed on another device. Refresh and try again.':response.status===404?'not_found':'Unable to save or load dashboard data. Please retry.'),{status:response.status});
 return response.json();
}
async function loadDashboard(){
 if(dashboardLoading)return;
 dashboardLoading=true;dashboardError='';homeError='';
 const paint=()=>{if(route==='dashboard'){const y=scrollY;render();window.scrollTo(0,y);}};
 paint();
 const home=dashboardRequest('dashboard/home').then(d=>{homeData=d}).catch(e=>{if(e.status!==404)homeError='The status line is unavailable; showing counts from the loaded records.'});
 const rest=dashboardRequest('dashboard').then(d=>{dashboardData=d}).catch(e=>{dashboardError=e.message});
 await home;paint();await rest;
 dashboardLoading=false;paint();
}
async function analyzeDashboardMorning(){
 if(morningLoading)return;
 morningLoading=true;morningError='';
 if(route==='dashboard')render();
 try{const result=await dashboardRequest('morning/generate',{method:'POST'});morningReport=result.report;dashboardData=await dashboardRequest('dashboard');}
 catch(error){morningError='The briefing could not be written. Please retry shortly.';}
 finally{morningLoading=false;if(route==='dashboard'){const y=scrollY;render();window.scrollTo(0,y)}}
}
window.addEventListener('hashchange',()=>{if(route==='dashboard')loadDashboard()});
const workspaceOpenAIDrawer=openAIDrawer;
openAIDrawer=function(){
 if(route!=='dashboard')return workspaceOpenAIDrawer();
 closeOverlay.focus=document.activeElement;drawerOpen=true;
 document.getElementById('overlay').innerHTML=`<div class="overlay"><aside class="drawer" role="dialog" aria-modal="true" aria-label="Dashboard follow-up"><div class="drawer-header"><h2>Follow up</h2>${btn('close','×','','aria-label="Close AI drawer"')}</div><div class="conversation">${chatHTML()}</div>${composer()}</aside></div>`;
 const messages=document.querySelector('#overlay .conversation');messages.scrollTop=messages.scrollHeight;
};
function dashboardChase(message){openAIDrawer();ask(message)}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-action]');if(!b)return;
 if(b.dataset.action==='dash-refresh')loadDashboard();
 if(b.dataset.action==='dash-analyze')analyzeDashboardMorning();
 if(b.dataset.action==='dash-suggest')dashboardChase(b.dataset.question);
 if(b.dataset.action==='decide-chat')dashboardChase(b.dataset.message);
 if(b.dataset.action==='decide-route')go(b.dataset.route);
 if(b.dataset.action==='dash-brief-chase'){const r=morningReport||dashboardData?.ai_briefing;if(r)dashboardChase('Draft one summary chase-up to myself based on these recommendations. Show the draft for my confirmation before sending: '+r.decide);}
 if(b.dataset.action==='dash-task-chase'){const task=dashboardData?.tasks.find(t=>t.id===b.dataset.task);if(task)dashboardChase('Draft a chase-up for this action. Show the draft for my confirmation before sending: '+task.title);}
 if(b.dataset.action==='dash-chase')dashboardChase(`Draft a chase-up for ${b.dataset.id}. Show me the draft for confirmation before sending.`);
});
// The home composer asks inside the follow-up drawer instead of leaving the page.
document.addEventListener('submit',e=>{const form=e.target;if(form.dataset.form==='chat'&&form.dataset.home){e.preventDefault();e.stopImmediatePropagation();const q=String(new FormData(form).get('visible-question')||'').trim();if(q)dashboardChase(q);}},true);
document.addEventListener('change',async e=>{
 const id=e.target.dataset.taskId;if(!id)return;
 const item=dashboardData.tasks.find(t=>t.id===id);e.target.disabled=true;
 try{await dashboardRequest('dashboard/tasks/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({done:e.target.checked,version:item.version})});dashboardData=await dashboardRequest('dashboard');if(route==='dashboard'){const y=scrollY;render();window.scrollTo(0,y)}}
 catch(error){e.target.checked=item.done;e.target.disabled=false;toast(error.message);}
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='dashboard-task-form')return;e.preventDefault();const form=e.target,input=form.elements.title,title=input.value.trim();if(!title)return;
 const b=form.querySelector('button');b.disabled=true;const id=form.dataset.requestId||crypto.randomUUID();form.dataset.requestId=id;
 try{await dashboardRequest('dashboard/tasks',{method:'POST',body:JSON.stringify({id,title})});dashboardData=await dashboardRequest('dashboard');if(route==='dashboard'){const y=scrollY;render();window.scrollTo(0,y)}}
 catch(error){toast(error.message);b.disabled=false;}
});
render();if(route==='dashboard')loadDashboard();

async function openBriefingEmail(day, button){
 if(document.getElementById('briefing-email-dialog'))return;
 button.disabled=true;
 try{
  let draft=await dashboardRequest('dashboard/briefings/'+encodeURIComponent(day)+'/email',{method:'POST'});
  const dialog=document.createElement('dialog');dialog.id='briefing-email-dialog';dialog.className='briefing-email-dialog';
  dialog.innerHTML=`<div class="section-heading"><h2>Morning summary email</h2><button type="button" class="email-close" aria-label="Close email">Close</button></div><p class="muted">Draft · ${esc(day)} · Review before sending</p><form><label>Subject<input name="subject" required maxlength="240"></label><label>Message<textarea name="body" required maxlength="12000"></textarea></label><p class="email-status" role="status"></p><div class="actions"><button type="submit" class="primary">Save draft</button><button type="button" class="email-copy">Copy email</button><button type="button" class="email-download">Download .eml</button></div></form>`;
  const form=dialog.querySelector('form'),status=dialog.querySelector('.email-status');
  form.elements.subject.value=draft.subject;form.elements.body.value=draft.body;
  let dirty=false,busy=false;
  const markSaved=()=>{dirty=false;status.textContent='Saved · '+formatWorkspaceTime(draft.updated_at)};markSaved();
  form.addEventListener('input',()=>{dirty=true;status.textContent='Unsaved changes'});
  const close=()=>{if(!busy&&(!dirty||confirm('Discard unsaved email changes?')))dialog.close()};
  dialog.querySelector('.email-close').onclick=close;
  dialog.addEventListener('cancel',e=>{e.preventDefault();close()});
  dialog.addEventListener('close',()=>dialog.remove());
  async function persist(){
   if(busy||!form.reportValidity())return false;
   const subject=form.elements.subject.value.trim(),body=form.elements.body.value.trim();
   if(!subject||!body||/[\r\n]/.test(subject)){status.textContent='Enter a subject and message.';return false}
   busy=true;form.querySelectorAll('button,input,textarea').forEach(b=>b.disabled=true);
   try{draft=await dashboardRequest('dashboard/briefings/'+encodeURIComponent(day)+'/email',{method:'PUT',body:JSON.stringify({subject,body,version:draft.version})});markSaved();return true}
   catch(e){status.textContent=e.message+' Your edits are still here.';return false}
   finally{busy=false;form.querySelectorAll('button,input,textarea').forEach(b=>b.disabled=false)}
  }
  form.addEventListener('submit',async e=>{e.preventDefault();await persist()});
  dialog.querySelector('.email-copy').onclick=async()=>{if(!await persist())return;try{await navigator.clipboard.writeText('Subject: '+draft.subject+'\n\n'+draft.body);status.textContent='Saved and copied'}catch{status.textContent='Saved. Select the subject and message to copy manually.'}};
  dialog.querySelector('.email-download').onclick=async()=>{if(!await persist())return;
   const encode=s=>btoa(Array.from(new TextEncoder().encode(s),b=>String.fromCharCode(b)).join(''));
   const encodedSubject=Array.from(draft.subject).reduce((parts,c)=>{if(new TextEncoder().encode(parts.at(-1)+c).length>42)parts.push(c);else parts[parts.length-1]+=c;return parts},['']).map(s=>'=?UTF-8?B?'+encode(s)+'?=').join('\r\n ');
   const eml='X-Unsent: 1\r\nSubject: '+encodedSubject+'\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n'+encode(draft.body.replace(/\r?\n/g,'\r\n')).match(/.{1,76}/g).join('\r\n')+'\r\n';
   const url=URL.createObjectURL(new Blob([eml],{type:'message/rfc822'})),a=document.createElement('a');a.href=url;a.download='morning-summary-'+day+'.eml';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='Saved and downloaded';
  };
  document.body.append(dialog);dialog.showModal();
 }catch(e){toast(e.message)}finally{button.disabled=false}
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-action="briefing-email"]');if(b)openBriefingEmail(b.dataset.day,b)});
