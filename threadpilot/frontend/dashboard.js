/* Dashboard data is shared through the backend; existing order-list views are untouched. */
let dashboardData=null,dashboardError='',dashboardLoading=false,taskView='pending',morningLoading=false,morningError='',morningReport=null;
const dashboardKeys=['in_progress','overdue','due_today','idle','priority'];
function miniTrend(key){
 let rows=dashboardData?.history||[],values=[],labels=[],caption='';
 if(rows.length>=2){values=rows.map(r=>r[key]);labels=rows.map(r=>r.date);caption='Recorded business-day snapshots';}
 else if(['in_progress','overdue','due_today'].includes(key)){
  for(let offset=6;offset>=0;offset--){const d=new Date(TODAY+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-offset);const day=d.toISOString().slice(0,10);labels.push(day);
   const active=orders.filter(o=>o.raw.order_date<=day&&(!o.completed||o.completed>day));
   values.push(active.filter(o=>key==='in_progress'||(key==='overdue'?o.due<day:o.due===day)).length);
  }
  caption='7-day history · recorded dates';
 }else if(key==='idle'){
  labels=['0d','1d','2d','3d','4d','5+d'];values=labels.map((_,i)=>activeOrders.filter(o=>Math.min(5,o.idle)===i).length);caption='Activity-gap distribution · 0–5+d';
 }else{
  labels=['overdue','high','medium','low','unknown'];values=labels.map(k=>(window.QUEUE_DATA?.orders||[]).filter(o=>o.risk.level===k).length);caption='Queue risk distribution';
 }
 const low=Math.min(...values),high=Math.max(...values),span=high-low||1;
 const points=values.map((v,i)=>`${4+i*112/(values.length-1)},${34-(v-low)*27/span}`).join(' ');
 return `<svg class="metric-spark" viewBox="0 0 120 42" role="img" aria-label="${esc(caption)}"><title>${esc(caption+'; '+labels.map((l,i)=>l+': '+values[i]).join('; '))}</title><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2.5"/><circle cx="116" cy="${34-(values.at(-1)-low)*27/span}" r="3" fill="currentColor"/></svg><small class="metric-change">${esc(caption)}</small>`;
}
function dashboardKpis(){
 const high=ranked.filter(o=>['Severe','Warning'].includes(level(o))),counts=dashboardData?.counts;
 return `<div class="grid kpis dashboard-kpis">${[['In progress',activeOrders.length,'orders?status=In%20progress','of 120 total orders'],['Overdue',overdue.length,'orders?due=Overdue','active orders only'],['Due today',dueToday.length,'orders?due=Today','review delivery readiness'],['Idle ≥5 days',idleOrders.length,'orders?idle=5','check the latest status'],['Queue risk',high.length,'risk','overdue, high or medium']].map(([title,value,url,sub],i)=>{
 const key=dashboardKeys[i],n=counts?.[key]??value,denom=i===0?orders.length:(counts?.in_progress??activeOrders.length);
 return `<a class="kpi" href="#/${url}"><span>${title}</span><div class="metric-value"><strong>${n}</strong>${miniTrend(key)}</div><small>${sub} ↗</small><div class="metric-comparison" role="img" aria-label="${n} of ${denom} orders"><i style="width:${denom?Math.min(100,n/denom*100):0}%"></i></div><small>${n} / ${denom} ${i===0?'total':'active'}</small></a>`;
 }).join('')}</div>`;
}
function briefingPoints(text,limit=2){
 const points=String(text||'').split(/\r?\n/).map(line=>line.replace(/^\s*[-*•]\s*/, '').trim()).filter(Boolean).slice(0,limit);
 return `<ul class="briefing-points">${points.map(point=>`<li>${esc(point)}</li>`).join('')}</ul>`;
}
function morningSummary(){
 const report=morningLoading?null:morningReport;
 return `<section class="card dashboard-brief"><div class="section-heading"><h2>Morning briefing</h2>${btn('dash-analyze',morningLoading?'Analyzing…':'Refresh analysis','',morningLoading?'disabled':'')}</div>${morningLoading?'<p class="muted" role="status">Reviewing production and priorities…</p>':''}${morningError?`<p class="callout error" role="alert">${esc(morningError)}</p>`:''}${report?`<dl class="summary-rows"><div><dt>Production</dt><dd>${briefingPoints(report.yesterday,4)}</dd></div><div><dt>Priorities</dt><dd>${briefingPoints(report.top_issue,4)}</dd></div><div><dt>Next steps</dt><dd>${briefingPoints(report.decide,4)}</dd></div></dl><div class="actions">${btn('dash-brief-chase','Draft chase-up')}</div>`:!morningLoading?'<p class="muted">Your briefing is not available yet. Select Refresh analysis to try again.</p>':''}</section>`;
}
function todoPanel(){
 const all=dashboardData?.tasks||[],pending=all.filter(t=>!t.done&&t.origin!=='auto'),done=all.filter(t=>t.done),risks=all.filter(t=>!t.done&&t.origin==='auto'&&t.reasons.length),visible=taskView==='done'?done:taskView==='risk'?risks:pending;
 const rank=new Map((dashboardData?.orders||[]).map(o=>[o.order_id,o]));
 visible.sort((a,b)=>{const x=rank.get(a.order_id),y=rank.get(b.order_id);return (x?.due_days??999)-(y?.due_days??999)||(y?.score??0)-(x?.score??0)});
 return `<section class="card dashboard-todos"><div class="section-heading"><h2>Today’s to-do list</h2><span class="badge">${pending.length} open</span></div><div class="todo-tabs" role="group" aria-label="Task status">${['pending','done','risk'].map(v=>`<button data-action="dash-filter" data-value="${v}" aria-pressed="${taskView===v}">${v==='pending'?'To do':v==='done'?'Handled':'Risk orders'} · ${v==='pending'?pending.length:v==='done'?done.length:risks.length}</button>`).join('')}</div><div class="todo-scroll" tabindex="0" aria-label="Tasks, scroll for more">${visible.map(t=>{
 const o=rank.get(t.order_id)||find(t.order_id);
 return `<article class="todo-item ${t.done?'is-done':''}"><label class="todo-check"><input type="checkbox" data-task-id="${esc(t.id)}" ${t.done?'checked':''} aria-label="Mark ${esc(t.title)} ${t.done?'pending':'handled'}"><span class="screenreader">Handled</span></label><div class="todo-content"><strong>${esc(t.title)}</strong><p class="muted">${t.origin==='manual'?'Personal task':esc(t.reasons.join(' · ')||'No longer flagged — review and close')}${t.done?' · ✓ Handled':''}</p>${o?`<div class="actions">${link('order','View order',t.order_id,'button small-button')}${btn('ask-order','Ask AI','small-button',`data-id="${esc(t.order_id)}"`)}${t.origin==='ai'?btn('dash-task-chase','Draft chase-up','small-button',`data-task="${esc(t.id)}"`):btn('dash-chase','Add chase-up','small-button',`data-id="${esc(t.order_id)}"`)}</div>`:t.origin==='ai'?`<div class="actions">${btn('dash-task-chase','Draft chase-up','small-button',`data-task="${esc(t.id)}"`)}</div>`:''}</div></article>`;
 }).join('')||`<p class="muted">${dashboardLoading?'Loading tasks…':taskView==='done'?'No handled tasks yet.':'No pending tasks.'}</p>`}</div><form id="dashboard-task-form"><label for="new-dashboard-task">Add a to-do</label><div class="todo-input"><input id="new-dashboard-task" name="title" required maxlength="300" placeholder="What needs to be done?" ${!dashboardData?'disabled':''}><button class="primary" type="submit" ${!dashboardData?'disabled':''}>Add</button></div></form></section>`;
}
function diagnosis(){
 const data=dashboardData,h=data?.health;
 if(!h)return '<section class="card dashboard-diagnosis"><h2>Order health</h2><p class="muted">Assessment is loading…</p></section>';
 const total=h.on_track+h.at_risk+h.late+(h.unknown||0),d=h.delivery,p=h.prior_delivery;
 return `<section class="card dashboard-diagnosis"><h2>Order health</h2><div class="diagnosis-scroll" tabindex="0" role="region" aria-label="Order health and recommendations"><div class="section-heading health-heading"><h3>Order health</h3><small>${total} orders in progress</small></div><div class="health-bar" role="img" aria-label="${h.on_track} on track, ${h.at_risk} at risk, ${h.late} late">${[['on-track',h.on_track],['at-risk',h.at_risk],['late',h.late]].map(([c,n])=>`<span class="${c}" style="width:${total?n/total*100:0}%"></span>`).join('')}</div><div class="health-counts">${[['On track',h.on_track,'on-track'],['At risk',h.at_risk,'at-risk'],['Late',h.late,'late']].map(([label,n,c])=>`<div><small><i class="${c}"></i>${label}</small><strong>${n}</strong></div>`).join('')}</div><small class="muted">${esc(h.basis)} · Late orders counted separately · ${h.unknown||0} unassessed</small><div class="delivery-rate"><p>On-time delivery · last 30 business-date days</p><strong>${d.rate===null?'—':d.rate+'%'}</strong><span> ${d.on_time} of ${d.total} completed orders</span>${d.rate!==null&&p.rate!==null?`<small>${d.rate-p.rate>=0?'+':''}${(d.rate-p.rate).toFixed(1)} pts vs prior 30 days</small>`:''}</div><div class="diagnosis-advice">${data.advice.slice(0,3).map(a=>`<article><h3>${esc(a.title)}</h3><p>${esc(a.text)}</p><div class="actions">${a.source?`<a class="button small-button" href="${esc(window.THREADPILOT_API_BASE)}/api/dashboard/sources/${esc(a.source)}">View sources</a>`:''}${a.orders.map(id=>link('order',id+(a.probabilities?.[id]?' · '+Math.round(a.probabilities[id]*100)+'% risk':''),id,'button small-button')).join('')}</div></article>`).join('')}</div></div></section>`;
}
dashboard=function(){return `<div class="dashboard-refresh">${head('Your factory, in focus.',TODAY+' · Three decisions to move the day forward.',btn('dash-refresh','Refresh'))}${dashboardError?`<div class="callout error" role="alert">${esc(dashboardError)} ${btn('dash-refresh','Retry')}</div>`:''}${dashboardKpis()}<div class="grid two dashboard-main">${morningSummary()}${todoPanel()}</div><div class="grid two spaced dashboard-lower"><section class="card" id="trend-card">${trendCard()}</section>${diagnosis()}</div></div>`};
async function dashboardRequest(path,options={}){
 const response=await window.threadpilotFetch(window.THREADPILOT_API_BASE+'/api/'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
 if(!response.ok)throw new Error(response.status===409?'This item changed on another device. Refresh and try again.':'Unable to save or load dashboard data. Please retry.');
 return response.json();
}
async function loadDashboard(analyze=true){
 if(dashboardLoading)return;
 dashboardLoading=true;dashboardError='';
 try{dashboardData=await dashboardRequest('dashboard');if(analyze)await analyzeDashboardMorning();}catch(e){dashboardError=e.message;}
 finally{dashboardLoading=false;if(route==='dashboard'){const y=scrollY;render();window.scrollTo(0,y);}}
}
async function analyzeDashboardMorning(){
 if(morningLoading)return;
 morningLoading=true;morningError='';
 morningReport=null;
 if(route==='dashboard')render();
 try{
  const result=await dashboardRequest('morning/generate',{method:'POST'});
  dashboardData=await dashboardRequest('dashboard');
  morningReport=result.report;
 }catch(error){morningError='Analysis is unavailable. Please retry shortly.';}
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
 if(b.dataset.action==='dash-brief-chase'&&morningReport)dashboardChase('Draft one summary chase-up to myself based on these recommendations. Show the draft for my confirmation before sending: '+morningReport.decide);
 if(b.dataset.action==='dash-task-chase'){const task=dashboardData?.tasks.find(t=>t.id===b.dataset.task);if(task)dashboardChase('Draft a chase-up for this action. Show the draft for my confirmation before sending: '+task.title);}
 if(b.dataset.action==='dash-filter'){taskView=b.dataset.value;const y=scrollY;render();window.scrollTo(0,y)}
 if(b.dataset.action==='dash-chase')dashboardChase(`Draft a chase-up for ${b.dataset.id}. Show me the draft for confirmation before sending.`);
});
document.addEventListener('change',async e=>{
 const id=e.target.dataset.taskId;if(!id)return;
 const item=dashboardData.tasks.find(t=>t.id===id);e.target.disabled=true;
 try{await dashboardRequest('dashboard/tasks/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({done:e.target.checked,version:item.version})});await loadDashboard(false);}
 catch(error){e.target.checked=item.done;e.target.disabled=false;toast(error.message);await loadDashboard(false);}
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='dashboard-task-form')return;e.preventDefault();const form=e.target,input=form.elements.title,title=input.value.trim();if(!title)return;
 const b=form.querySelector('button');b.disabled=true;const id=form.dataset.requestId||crypto.randomUUID();form.dataset.requestId=id;
 try{await dashboardRequest('dashboard/tasks',{method:'POST',body:JSON.stringify({id,title})});await loadDashboard(false);}
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
