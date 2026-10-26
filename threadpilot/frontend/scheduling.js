/* Risk → impact → explicit manager decision. */
const queueRank={overdue:0,high:1,medium:2,unknown:3,low:4};
async function scheduleRequest(path,options={}){
 const response=await window.threadpilotFetch(window.THREADPILOT_API_BASE+'/api/scheduling/'+path,
  {...options,cache:'no-store',headers:{'Content-Type':'application/json',...options.headers}});
 const body=await response.json();
 if(!response.ok)throw new Error(body.error?.message||body.detail||'Unable to load scheduling data.');
 return body;
}
function expediteEntry(id){return btn('expedite-preview','Analyze expedite impact','primary',`data-id="${esc(id)}"`)}
riskPage=function(){
 const rows=[...(window.QUEUE_DATA?.orders||[])].sort((a,b)=>queueRank[a.risk.level]-queueRank[b.risk.level]||a.due_date.localeCompare(b.due_date));
 const o=rows.find(x=>x.order_id===riskId)||rows[0];
 if(!o)return head('Queue risk','No in-progress orders.');
 riskId=o.order_id;
 const late=rows.filter(r=>r.risk.level==='overdue').length,risky=rows.filter(r=>['high','medium'].includes(r.risk.level)).length;
 return head('Risk orders',`${late} late · ${risky} at risk · ${rows.length-late-risky} on track or unassessed · ${window.QUEUE_DATA.business_date}`,btn('queue-refresh','Refresh')+btn('schedule-history','Decision history'))+
 `<div class="grid risk-grid"><section class="card"><h2>Risk orders</h2><div class="table-wrap"><table><thead><tr><th>Order</th><th>Status</th><th>Best-case finish</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr class="${r.order_id===riskId?'selected-row':''}"><td>${esc(r.order_id)}<br>${esc(r.customer)}</td><td><span class="badge ${riskClass(r.risk.level)==='late'?'severe':riskClass(r.risk.level)==='at-risk'?'warning':'watch'}">${esc(riskWord(r.risk.level))}</span></td><td>${esc(r.risk.best_date||'Unavailable')}</td><td>${btn('risk-select','Review','',`data-id="${esc(r.order_id)}"`)}</td></tr>`).join('')}</tbody></table></div></section>
 <aside class="card risk-detail"><h2>${esc(o.order_id)} <span class="badge ${riskClass(o.risk.level)==='late'?'severe':riskClass(o.risk.level)==='at-risk'?'warning':'watch'}">${esc(riskWord(o.risk.level))}</span></h2><p>${esc(o.risk.reason)}</p><p>Due ${esc(o.due_date)} · ${esc(o.current_stage)}</p>${forecastLine(o.order_id)}${expediteEntry(o.order_id)}${factorHelp()}<p>Approved priority queue: ${esc(window.QUEUE_DATA.schedule.priority.join(' → ')||'Earliest due first')}</p><div class="actions">${link('order','View order',o.order_id)}${btn('queue-chase','Draft chase-up','',`data-id="${esc(o.order_id)}"`)}</div></aside></div>`;
};
const queueOriginalOrderDetail=orderDetail;
orderDetail=function(){const o=current();return queueOriginalOrderDetail()+(o.status==='In progress'?`<section class="card spaced"><h2>Dispatch decision</h2><p>Compare the same queue before and after moving this order to the front.</p>${expediteEntry(o.id)}</section>`:'')};

async function openExpedite(id,button,draftId=null){
 button.disabled=true;
 try{
  const draft=await scheduleRequest(draftId?'drafts/'+draftId:'orders/'+encodeURIComponent(id)+'/draft',draftId?{}:{method:'POST'});
  id=draft.order_id;const p=draft.analysis;
  const d=document.createElement('dialog');d.className='expedite-dialog';d.setAttribute('aria-labelledby','expedite-title');
  const labels={now:'Expedite: worth it',later:'Keep the current order',trade_off:'Trade-off: your call',investigate:'Suspected stall: check first',unavailable:'Cannot assess'};
  const toDays=s=>s?dayDiff(s,p.business_date):null,before=toDays(p.finish_before),after=toDays(p.finish_after),span=Math.max(before||0,after||0,1);
  const unchanged=p.finish_before&&p.finish_before===p.finish_after;
  const verdict=p.recommendation==='unavailable'?p.reason:unchanged?`Already first in its queue: expediting changes nothing (finish stays ${date(p.finish_before)}). The options left are an outside workshop or a new date with the customer.`:`Saves ${p.gain??0} order-day${p.gain===1?'':'s'} of lateness on ${id}, adds ${p.cost??0} to other orders (net ${p.net??0}); ${p.affected.filter(r=>r.newly_late).length} order${p.affected.filter(r=>r.newly_late).length===1?'':'s'} would become late.`;
  const bar=(label,days,finish,cls)=>`<div class="ba-row"><span>${label}</span><div class="ba-track"><i class="${cls}" style="width:${days===null?0:Math.max(2,days/span*100)}%"></i></div><strong>${finish?date(finish):'—'}${days!==null?` <small>· ${days} d</small>`:''}</strong></div>`;
  d.innerHTML=`<div class="section-heading"><h2 id="expedite-title">${esc(id)} · Expedite review</h2><button type="button" data-close>Close</button></div>
   <p class="muted">${esc(p.business_date)} · ${esc(riskWord(p.risk.level))}</p><h3 class="verdict">${esc(labels[p.recommendation])}</h3><p class="verdict-line">${esc(verdict)}</p>
   <div class="before-after" role="img" aria-label="Finish ${esc(p.finish_before||'unavailable')} before, ${esc(p.finish_after||'unavailable')} after">${bar('Before',before,p.finish_before,'before')}${bar('After',after,p.finish_after,unchanged?'before':'after')}</div>
   ${unchanged?'':`<div class="grid three"><p>Lateness saved<br><strong>${p.gain??'—'}</strong></p><p>Added to other orders<br><strong>${p.cost??'—'}</strong></p><p>Net benefit<br><strong>${p.net??'—'}</strong></p></div><p class="muted">Unit: order-working-days. No monetary or customer weights.</p>`}
   ${unchanged?`<div class="actions">${link('feasibility','Compare an outside workshop')}<button type="button" data-follow="chase">Draft a new-date message</button></div>`:''}
   <details ${p.affected.length?'open':''}><summary>Affected orders (${p.affected.length})</summary><div class="table-wrap"><table><thead><tr><th>Order</th><th>Before → after</th><th>Extra days</th><th>Added lateness</th><th>Newly late?</th></tr></thead><tbody>${p.affected.map(r=>`<tr><td>${esc(r.order_id)}</td><td>${esc(r.finish_before)} → ${esc(r.finish_after)}</td><td>${r.extra_days}</td><td>${r.added_lateness}</td><td>${r.newly_late?'Yes':'No'}</td></tr>`).join('')||'<tr><td colspan="5">No other order moves.</td></tr>'}</tbody></table></div></details>
   <details><summary>Capacity and assumptions</summary><p>${esc(Object.entries(p.capacity||{}).map(([k,v])=>`${k.toLowerCase()} ${v===null?'n/a':Math.round(v)}/day`).join(' · '))}</p><ul>${p.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul></details>
   <form><label>Manager name<input name="reviewer" required maxlength="100" autocomplete="name"></label><label>Decision reason / note<textarea name="note" required maxlength="2000"></textarea></label>
   <label>Decision<select name="decision"><option value="save">Save the advice, decide later</option><option value="reject">Reject the expedite</option><option value="apply">Approve and re-sequence</option></select></label>
   <section class="review-draft-editor"><h3>AI draft of the decision reason</h3><p data-draft-status role="status"></p><button type="button" data-draft-refresh>Re-analyse (keep my text)</button><button type="button" data-draft-reload>Load the latest saved draft</button><button type="button" data-draft-recover hidden>Restore unsaved text</button>
   <label>Drafting instruction<textarea name="draft_instruction" maxlength="1500" placeholder="e.g. keep the current order and say why in two lines; or: shorter and more formal"></textarea></label>
   <div class="actions"><button type="button" data-draft-generate>Draft with AI</button><button type="button" data-draft-chat>Continue in chat</button></div>
   <p>The AI candidate never overwrites the form; adopt it, then submit.</p><pre data-draft-candidate></pre><button type="button" data-draft-adopt>Adopt into the form (replaces the reason)</button></section>
   <label><input name="reviewed" type="checkbox" required> I reviewed the affected orders and assumptions.</label>
   <p>Approving places this order before all existing priorities in each remaining stage, until completion or a later approved adjustment. It changes this application's dispatch plan.</p>
   <div class="actions"><button type="submit" value="save">Save advice</button><button type="submit" value="reject">Reject</button><button type="submit" value="apply" class="primary" ${p.can_apply?'':'disabled'}>Approve and re-sequence</button></div><p role="status" data-status></p></form>
   <div class="actions"><button type="button" data-follow="chase">Generate chase-up</button><button type="button" data-follow="note">Save workflow note</button><button type="button" data-follow="reminder">Set reminder</button></div>`;
  document.body.append(d);d.showModal();let busy=false,decided=false;
  d.querySelector('[data-close]').onclick=()=>{if(!busy)d.close()};
  d.addEventListener('cancel',e=>{if(busy)e.preventDefault()});
  d.addEventListener('close',()=>d.remove());
  const form=d.querySelector('form'),status=d.querySelector('[data-status]');
  const editor=installReviewDraft(d,draft);
  d.addEventListener('close',()=>editor.dispose());
  form.addEventListener('submit',async e=>{
   e.preventDefault();if(busy||decided||!form.reportValidity())return;
   if(editor.busy)return;
   const decision=e.submitter.value;
   if(form.elements.decision.value!==decision){status.textContent='Choose the matching decision in the list, check the reason and tick the confirmation again.';form.elements.reviewed.checked=false;return;}
   if(decision==='apply'&&!confirm(`Move ${id} ahead of all current priorities? ${p.affected.filter(r=>r.newly_late).length} order(s) become late in this scenario.`))return;
   busy=true;form.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='Saving reviewed decision…';
   try{
    await editor.flush();const latest=editor.current();
    const result=await scheduleRequest('reviews/'+latest.review_id+'/decision',{method:'POST',headers:{'X-Confirm-Write':'true'},body:JSON.stringify({decision,reviewed_by:form.elements.reviewer.value,note:form.elements.note.value,draft_id:latest.id,draft_version:latest.version})});
    decided=true;editor.finish();status.textContent=`Decision ${result.status}. Saved to shared history.`;
    window.QUEUE_DATA=await scheduleRequest('risk');await loadDashboard();render();
    if(result.dispatch_notice){const n=result.dispatch_notice;window.__dispatchNotice=n;modal('Tell the floor about this change?',`<p>${esc(n.text)}</p><p class="muted">${esc(n.note)}</p>`,'dispatch-notice',`Draft to ${esc(n.department.toLowerCase())} in chat`);}
   }catch(error){status.textContent=error.message;}
   finally{busy=false;if(!decided)form.querySelectorAll('button').forEach(b=>b.disabled=b.value==='apply'&&!p.can_apply);}
  });
  d.querySelectorAll('[data-follow]').forEach(b=>b.onclick=()=>{
   if(busy)return;
   const note=form.elements.note.value.trim();
   const q=b.dataset.follow==='chase'?`Draft a chase-up for ${id}. Ask production to review its queue priority and confirm remaining work. Show the draft before sending.`:
    b.dataset.follow==='note'?`Save an internal note for ${id}: ${note||p.reason} Analysis net benefit: ${p.net??'unavailable'} order-working-days. Schedule change requires manager review.`:
    `Set a no-activity reminder for ${id}. Ask me for the deadline before saving.`;
   d.close();state.selected=id;save();go('ai');ask(q);
  });
 }catch(e){toast(e.message)}finally{button.disabled=false}
}
async function showScheduleHistory(){
 try{const rows=await scheduleRequest('history'),d=document.createElement('dialog');d.className='expedite-dialog';
 d.innerHTML=`<h2>Manager decision history</h2><p>Decisions record the reviewer name, reason and affected orders.</p>${rows.map(r=>`<details><summary>${esc(r.order_id)} · ${esc(r.status)} · ${esc(r.decided_at)}</summary><p>${esc(r.reviewed_by)}: ${esc(r.note)}</p><p>Saved net benefit: ${r.payload.net??'Unavailable'} · ${esc(r.payload.business_date)}</p><pre>${esc(JSON.stringify(r.payload.affected,null,2))}</pre></details>`).join('')||'<p>No reviewed decisions yet.</p>'}<button>Close</button>`;
 document.body.append(d);d.querySelector('button').onclick=()=>d.close();d.onclose=()=>d.remove();d.showModal();
 }catch(e){toast(e.message)}
}
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-action]');if(!b)return;
 if(b.dataset.action==='review-draft-open')openExpedite(b.dataset.id,b,b.dataset.draft);
 if(b.dataset.action==='expedite-preview')openExpedite(b.dataset.id,b);
 if(b.dataset.action==='queue-refresh')location.reload();
 if(b.dataset.action==='schedule-history')showScheduleHistory();
 if(b.dataset.action==='queue-chase'){go('ai');ask(`Draft a chase-up for ${b.dataset.id}. Show it before sending.`)}
});
render();
