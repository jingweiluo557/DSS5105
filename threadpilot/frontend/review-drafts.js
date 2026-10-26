/* The server is authoritative; a local recovery copy also survives refresh during autosave. */
function installReviewDraft(dialog, initial){
 let draft=initial,timer,chain=Promise.resolve(),closed=false,finished=initial.status==='submitted',working=false,suppressSave=false;
 const form=dialog.querySelector('form'),message=dialog.querySelector('[data-draft-status]');
 const key='threadpilot-review-recovery:'+window.THREADPILOT_API_BASE+':'+draft.id;
 const fields=()=>({text:form.elements.note.value,reviewer:form.elements.reviewer.value,decision:form.elements.decision.value});
 const dirty=()=>{const v=fields();return ['text','reviewer','decision'].some(k=>v[k]!==draft[k])};
 const remember=()=>{try{localStorage.setItem(key,JSON.stringify({...fields(),baseVersion:draft.version}))}catch{}};
 const clear=()=>{try{localStorage.removeItem(key)}catch{}};
 const recovery=()=>{try{return JSON.parse(localStorage.getItem(key)||'null')}catch{return null}};
 function show(){
  dialog.querySelector('[data-draft-candidate]').textContent=draft.candidate||'No AI candidate yet.';
  dialog.querySelector('[data-draft-adopt]').disabled=!draft.candidate||draft.stale||finished;
  dialog.querySelector('[data-draft-generate]').disabled=draft.stale||finished;
  message.textContent=draft.stale?'The analysis is out of date or the data changed. Your text is kept; re-analyse and check it.':`Draft v${draft.version} saved; not submitted yet.${draft.analysis_refreshed?' Re-analysed: the kept reason may quote old numbers; check it before ticking the confirmation.':''}`;
 }
 function fill(){form.elements.note.value=draft.text;form.elements.reviewer.value=draft.reviewer;form.elements.decision.value=draft.decision;form.elements.reviewed.checked=false;show()}
 fill();
 if(finished){form.querySelectorAll('input,textarea,select,button').forEach(e=>e.disabled=true);message.textContent='This draft was submitted and is read-only. Close and re-analyse to start a new review.'}
 const cached=recovery();
 if(cached&&!finished){
  if(cached.baseVersion===draft.version){for(const [k,n] of [['text','note'],['reviewer','reviewer'],['decision','decision']])form.elements[n].value=cached[k];message.textContent='Restored unsaved text from this device; syncing.';timer=setTimeout(()=>flush().catch(report),500)}
  else{dialog.querySelector('[data-draft-recover]').hidden=false;message.textContent='Unsaved text on this device and a newer version on the server: restore yours or keep the server version.'}
 }
 function report(error){if(!closed)message.textContent=error.message+' Your text is kept; on a version conflict, load the latest draft.'}
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
  form.elements.reviewed.checked=false;remember();clearTimeout(timer);message.textContent='Saving draft…';timer=setTimeout(()=>flush().catch(report),500);
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
  message.textContent='Drafting with AI; your form text stays as it is…';
  draft=await scheduleRequest('drafts/'+draft.id+'/generate',{method:'POST',body:JSON.stringify({version:draft.version,instruction:form.elements.draft_instruction.value.trim()||'Draft the decision reason from the chosen decision and the analysis.'})});show();
 });
 dialog.querySelector('[data-draft-adopt]').onclick=()=>action(async()=>{
  if(form.elements.note.value.trim()&&!confirm('Adopting the AI candidate replaces the current reason, including your edits. Continue?'))return;
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
  if(!confirm('Load the text kept on this device into the form, replacing what is shown?'))return;
  form.elements.note.value=old.text;form.elements.reviewer.value=old.reviewer;form.elements.decision.value=old.decision;
  form.elements.reviewed.checked=false;remember();flush().catch(report);dialog.querySelector('[data-draft-recover]').hidden=true;
 };
 dialog.querySelector('[data-draft-chat]').onclick=()=>action(async()=>{
  window.reviewDraftContext=draft.id;sessionStorage.setItem('threadpilot-review-context',draft.id);
  dialog.close();state.selected=draft.order_id;save();go('ai');
  ask(`Continue editing the decision reason draft for ${draft.order_id}. ${form.elements.draft_instruction.value.trim()||'Draft the reason from the current decision.'}`);
 });
 return {flush,current:()=>draft,get busy(){return working},finish(){finished=true;clearTimeout(timer);clear();form.querySelectorAll('input,textarea,select,button').forEach(e=>e.disabled=true)},dispose(){closed=true;clearTimeout(timer);if(!finished&&!suppressSave&&dirty()){remember();flush().catch(()=>{})}}};
}

window.reviewDraftContext=sessionStorage.getItem('threadpilot-review-context')||null;
const reviewChatHTML=chatHTML;
chatHTML=function(){
 const last=state.chat.findLast(m=>m.role==='assistant');
 return reviewChatHTML()+(last?.reviewDraft?`<div class="bubble"><p>Decision reason draft: adopting the text does not change the schedule.</p>${btn('review-draft-open','Open the review form','primary',`data-id="${esc(last.reviewDraft.order_id)}" data-draft="${esc(last.reviewDraft.draft_id)}"`)}</div>`:'');
};
document.addEventListener('click',e=>{if(['new-chat','confirm-reset'].includes(e.target.closest('[data-action]')?.dataset.action)){window.reviewDraftContext=null;sessionStorage.removeItem('threadpilot-review-context')}},true);
