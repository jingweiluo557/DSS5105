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
 return head('Risk and dispatch decisions',`${window.QUEUE_DATA.business_date} · Current orders and approved priorities`,btn('queue-refresh','Refresh')+btn('schedule-history','Decision history'))+
 `<div class="grid risk-grid"><section class="card"><h2>Risk orders</h2><div class="table-wrap"><table><thead><tr><th>Order</th><th>Risk</th><th>Projected finish</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.order_id)}<br>${esc(r.customer)}</td><td>${esc(r.risk.level)}</td><td>${esc(r.risk.best_date||'Unavailable')}</td><td>${btn('risk-select','Review','',`data-id="${esc(r.order_id)}"`)}</td></tr>`).join('')}</tbody></table></div></section>
 <aside class="card risk-detail"><h2>${esc(o.order_id)}</h2><p>${esc(o.risk.reason)}</p><p>Due ${esc(o.due_date)} · ${esc(o.current_stage)}</p>${expediteEntry(o.order_id)}${factorHelp()}<p>Approved priority queue: ${esc(window.QUEUE_DATA.schedule.priority.join(' → ')||'Earliest due first')}</p><div class="actions">${link('order','View order',o.order_id)}${btn('queue-chase','Draft chase-up','',`data-id="${esc(o.order_id)}"`)}</div></aside></div>`;
};
const queueOriginalOrderDetail=orderDetail;
orderDetail=function(){const o=current();return queueOriginalOrderDetail()+(o.status==='In progress'?`<section class="card spaced"><h2>Dispatch decision</h2><p>Compare the same queue before and after moving this order to the front.</p>${expediteEntry(o.id)}</section>`:'')};

async function openExpedite(id,button,draftId=null){
 button.disabled=true;
 try{
  const draft=await scheduleRequest(draftId?'drafts/'+draftId:'orders/'+encodeURIComponent(id)+'/draft',draftId?{}:{method:'POST'});
  id=draft.order_id;const p=draft.analysis;
  const d=document.createElement('dialog');d.className='expedite-dialog';d.setAttribute('aria-labelledby','expedite-title');
  const labels={now:'Recommend expedite',later:'Keep current order',trade_off:'Manager trade-off',investigate:'Investigate suspected stall',unavailable:'Cannot assess'};
  d.innerHTML=`<div class="section-heading"><h2 id="expedite-title">${esc(id)} · Expedite review</h2><button type="button" data-close>Close</button></div>
   <p>${esc(p.business_date)} · Risk: ${esc(p.risk.level)}</p><h3>${esc(labels[p.recommendation])}</h3><p>${esc(p.reason)}</p>
   <p>Projected finish: <strong>${esc(p.finish_before||'Unavailable')}</strong> → <strong>${esc(p.finish_after||'Unavailable')}</strong></p>
   <div class="grid three"><p>Lateness saved<br><strong>${p.gain??'—'}</strong></p><p>Added to other orders<br><strong>${p.cost??'—'}</strong></p><p>Net benefit<br><strong>${p.net??'—'}</strong></p></div><p class="muted">Unit: order-working-days. No monetary or customer weights.</p>
   <h3>Affected orders (${p.affected.length})</h3><div class="table-wrap"><table><thead><tr><th>Order</th><th>Before → after</th><th>Extra days</th><th>Added lateness</th><th>Newly late?</th></tr></thead><tbody>${p.affected.map(r=>`<tr><td>${esc(r.order_id)}</td><td>${esc(r.finish_before)} → ${esc(r.finish_after)}</td><td>${r.extra_days}</td><td>${r.added_lateness}</td><td>${r.newly_late?'Yes':'No'}</td></tr>`).join('')||'<tr><td colspan="5">No affected orders identified.</td></tr>'}</tbody></table></div>
   <details><summary>Capacity and assumptions</summary><p>${esc(JSON.stringify(p.capacity))}</p><ul>${p.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul></details>
   <form><label>Manager name<input name="reviewer" required maxlength="100" autocomplete="name"></label><label>Decision reason / note<textarea name="note" required maxlength="2000"></textarea></label>
   <label>Decision intention / 决策倾向<select name="decision"><option value="save">暂缓决定 / Save advice</option><option value="reject">不批准插队 / Reject</option><option value="apply">批准插队 / Apply</option></select></label>
   <section class="review-draft-editor"><h3>AI 审核理由草稿</h3><p data-draft-status role="status"></p><button type="button" data-draft-refresh>重新分析（保留表单文字）</button><button type="button" data-draft-reload>加载服务器最新草稿</button><button type="button" data-draft-recover hidden>恢复本机未保存文字</button>
   <label>起草或修改要求<textarea name="draft_instruction" maxlength="1500" placeholder="例如：先不插队，简短说明原因；或：再短一点，更正式一些"></textarea></label>
   <div class="actions"><button type="button" data-draft-generate>AI 起草 / 修改</button><button type="button" data-draft-chat>在聊天中继续修改</button></div>
   <p>AI 候选不会自动覆盖表单。采用后仍需你确认提交。</p><pre data-draft-candidate></pre><button type="button" data-draft-adopt>采用到表单（替换当前理由）</button></section>
   <label><input name="reviewed" type="checkbox" required> I reviewed the affected orders and assumptions.</label>
   <p>Applying places this order before all existing priorities in each remaining stage, until completion or a later approved adjustment. It changes this application's dispatch plan.</p>
   <div class="actions"><button type="submit" value="save">Save advice</button><button type="submit" value="reject">Reject</button><button type="submit" value="apply" class="primary" ${p.can_apply?'':'disabled'}>Approve and adjust schedule</button></div><p role="status" data-status></p></form>
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
   if(form.elements.decision.value!==decision){status.textContent='请先选择对应的决策倾向，核对理由并重新勾选确认。';form.elements.reviewed.checked=false;return;}
   if(decision==='apply'&&!confirm(`Move ${id} ahead of all current priorities? ${p.affected.filter(r=>r.newly_late).length} order(s) become late in this scenario.`))return;
   busy=true;form.querySelectorAll('button').forEach(b=>b.disabled=true);status.textContent='Saving reviewed decision…';
   try{
    await editor.flush();const latest=editor.current();
    const result=await scheduleRequest('reviews/'+latest.review_id+'/decision',{method:'POST',headers:{'X-Confirm-Write':'true'},body:JSON.stringify({decision,reviewed_by:form.elements.reviewer.value,note:form.elements.note.value,draft_id:latest.id,draft_version:latest.version})});
    decided=true;editor.finish();status.textContent=`Decision ${result.status}. Saved to shared history.`;
    window.QUEUE_DATA=await scheduleRequest('risk');await loadDashboard();render();
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
