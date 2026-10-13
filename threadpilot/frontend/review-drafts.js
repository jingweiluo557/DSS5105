/* The server is authoritative; a local recovery copy also survives refresh during autosave. */
function installReviewDraft(dialog, initial){
 let draft=initial,timer,chain=Promise.resolve(),closed=false,finished=initial.status==='submitted',working=false,suppressSave=false;
 const form=dialog.querySelector('form'),message=dialog.querySelector('[data-draft-status]');
 const key='threadpilot-review-recovery:'+draft.id;
 const fields=()=>({text:form.elements.note.value,reviewer:form.elements.reviewer.value,decision:form.elements.decision.value});
 const dirty=()=>{const v=fields();return ['text','reviewer','decision'].some(k=>v[k]!==draft[k])};
 const remember=()=>{try{localStorage.setItem(key,JSON.stringify({...fields(),baseVersion:draft.version}))}catch{}};
 const clear=()=>{try{localStorage.removeItem(key)}catch{}};
 const recovery=()=>{try{return JSON.parse(localStorage.getItem(key)||'null')}catch{return null}};
 function show(){
  dialog.querySelector('[data-draft-candidate]').textContent=draft.candidate||'尚无候选草稿。';
  dialog.querySelector('[data-draft-adopt]').disabled=!draft.candidate||draft.stale||finished;
  dialog.querySelector('[data-draft-generate]').disabled=draft.stale||finished;
  message.textContent=draft.stale?'分析已过期或数据变化。文字已保留，请重新分析并核对。':`草稿 v${draft.version} 已保存；尚未提交审核。${draft.analysis_refreshed?' 已重新分析：保留的理由可能使用旧数字，请核对后再勾选确认。':''}`;
 }
 function fill(){form.elements.note.value=draft.text;form.elements.reviewer.value=draft.reviewer;form.elements.decision.value=draft.decision;form.elements.reviewed.checked=false;show()}
 fill();
 if(finished){form.querySelectorAll('input,textarea,select,button').forEach(e=>e.disabled=true);message.textContent='此草稿已提交，只读。请关闭后重新分析以创建新审核。'}
 const cached=recovery();
 if(cached&&!finished){
  if(cached.baseVersion===draft.version){for(const [k,n] of [['text','note'],['reviewer','reviewer'],['decision','decision']])form.elements[n].value=cached[k];message.textContent='已恢复本机未保存文字，正在同步。';timer=setTimeout(()=>flush().catch(report),500)}
  else{dialog.querySelector('[data-draft-recover]').hidden=false;message.textContent='检测到本机未保存文字与服务器新版本；可选择恢复本机文字或继续使用服务器版本。'}
 }
 function report(error){if(!closed)message.textContent=error.message+' 当前表单文字已保留；如有版本冲突，请加载最新草稿。'}
 function flush(){
  clearTimeout(timer);
  const run=async()=>{
   if(finished||!dirty())return;
   const values=fields();remember();
   const result=await scheduleRequest('drafts/'+draft.id,{method:'PATCH',body:JSON.stringify({version:draft.version,...values})});
   draft=result;
   if(!dirty())clear();else remember();
   if(!closed)show();
  };
  chain=chain.catch(()=>{}).then(run);return chain;
 }
 for(const name of ['note','reviewer','decision'])form.elements[name].addEventListener('input',()=>{
  form.elements.reviewed.checked=false;remember();clearTimeout(timer);message.textContent='正在保存草稿…';timer=setTimeout(()=>flush().catch(report),500);
 });
 async function action(fn){
  if(working||finished)return;working=true;
  // Freeze the form during the request; generated candidates still never replace it.
  const controls=[...form.querySelectorAll('input,textarea,select,button')];
  const was=controls.map(e=>e.disabled);controls.forEach(e=>e.disabled=true);
  try{await flush();await fn()}
  catch(error){report(error)}
  finally{working=false;controls.forEach((e,i)=>e.disabled=was[i]);if(!closed){dialog.querySelector('[data-draft-adopt]').disabled=!draft.candidate||draft.stale;dialog.querySelector('[data-draft-generate]').disabled=draft.stale}}
 }
 dialog.querySelector('[data-draft-generate]').onclick=()=>action(async()=>{
  message.textContent='AI 正在起草，原有表单文字保持不变…';
  draft=await scheduleRequest('drafts/'+draft.id+'/generate',{method:'POST',body:JSON.stringify({version:draft.version,instruction:form.elements.draft_instruction.value.trim()||'请根据所选决策倾向和分析结果起草审核理由。'})});show();
 });
 dialog.querySelector('[data-draft-adopt]').onclick=()=>action(async()=>{
  if(form.elements.note.value.trim()&&!confirm('采用 AI 候选将替换当前理由，包括手动修改。继续？'))return;
  draft=await scheduleRequest('drafts/'+draft.id+'/adopt',{method:'POST',body:JSON.stringify({version:draft.version})});clear();fill();
 });
 dialog.querySelector('[data-draft-refresh]').onclick=()=>action(async()=>{
  draft=await scheduleRequest('drafts/'+draft.id+'/refresh',{method:'POST',body:JSON.stringify({version:draft.version})});
  dialog.close();await openExpedite(draft.order_id,{disabled:false},draft.id);
 });
 dialog.querySelector('[data-draft-reload]').onclick=async()=>{
  if(working||finished)return;
  if(dirty())remember();clearTimeout(timer);await chain.catch(()=>{});
  try{draft=await scheduleRequest('drafts/'+draft.id);suppressSave=true;dialog.close();await openExpedite(draft.order_id,{disabled:false},draft.id)}catch(error){report(error)}
 };
 dialog.querySelector('[data-draft-recover]').onclick=()=>{
  const old=recovery();if(!old)return;
  if(!confirm('将本机保留文字载入表单，替换当前显示内容？'))return;
  form.elements.note.value=old.text;form.elements.reviewer.value=old.reviewer;form.elements.decision.value=old.decision;
  form.elements.reviewed.checked=false;remember();flush().catch(report);dialog.querySelector('[data-draft-recover]').hidden=true;
 };
 dialog.querySelector('[data-draft-chat]').onclick=()=>action(async()=>{
  window.reviewDraftContext=draft.id;sessionStorage.setItem('threadpilot-review-context',draft.id);
  dialog.close();state.selected=draft.order_id;save();go('ai');
  ask(`请继续修改 ${draft.order_id} 的审核理由草稿。${form.elements.draft_instruction.value.trim()||'请根据当前决策倾向起草理由。'}`);
 });
 return {flush,current:()=>draft,get busy(){return working},finish(){finished=true;clearTimeout(timer);clear();form.querySelectorAll('input,textarea,select,button').forEach(e=>e.disabled=true)},dispose(){closed=true;clearTimeout(timer);if(!finished&&!suppressSave&&dirty()){remember();flush().catch(()=>{})}}};
}

window.reviewDraftContext=sessionStorage.getItem('threadpilot-review-context')||null;
const reviewChatHTML=chatHTML;
chatHTML=function(){
 const last=state.chat.findLast(m=>m.role==='assistant');
 return reviewChatHTML()+(last?.reviewDraft?`<div class="bubble"><p>审核理由草稿：采用文字不会执行排程。</p>${btn('review-draft-open','打开审核表单','primary',`data-id="${esc(last.reviewDraft.order_id)}" data-draft="${esc(last.reviewDraft.draft_id)}"`)}</div>`:'');
};
document.addEventListener('click',e=>{if(['new-chat','confirm-reset'].includes(e.target.closest('[data-action]')?.dataset.action)){window.reviewDraftContext=null;sessionStorage.removeItem('threadpilot-review-context')}},true);
