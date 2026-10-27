/* Current backend contract only: no embedded simulation dataset or legacy /chat payload. */
(() => {
 const $=s=>document.querySelector(s),base=window.THREADPILOT_API_BASE;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let data=null,session=null,selected=null,generating=false;
 async function request(path,options={}){
  if(window.THREADPILOT_CONFIG_ERROR)throw Error(window.THREADPILOT_CONFIG_ERROR);
  const r=await window.threadpilotFetch(base+path,{...options,cache:'no-store',headers:{'Content-Type':'application/json'}});
  const body=await r.json();if(!r.ok)throw Error(body.error?.message||body.detail||'Unable to connect to the backend');return body;
 }
 function sectionBody(key,text){
  if(!['top_issue','decide'].includes(key))return `<p>${esc(text)}</p>`;
  const points=String(text??'').split(/\r?\n/).map(line=>line.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim()).filter(Boolean);
  return `<ul class="brief-points">${points.map(point=>`<li>${esc(point)}</li>`).join('')}</ul>`;
 }
 function render(){
  const report=data.reports.find(r=>r.id===selected)||data.reports[0];
  if(!report){$('#report').innerHTML='<section class="brief-card">No briefing yet. Select Generate briefing to analyze the current database snapshot.</section>';return}
  selected=report.id;
  const stale=report.fingerprint!==data.current_fingerprint;
  $('#report').innerHTML=`<section class="brief-card"><strong>Model: ${esc(report.model)}</strong><p>Business date: ${esc(report.business_date)}<br>Latest production record: ${esc(report.latest_production_date||'Not available')}</p>${!/^morning-v([7-9]|[1-9]\d)-/.test(report.generation_version||'')?'<p>Archived report. Generate a new briefing for the current English bullet-point format.</p>':''}${stale?'<p>This report uses an older snapshot. Generate a new briefing for current data.</p>':''}</section><div class="brief-grid">${[['Production review','yesterday'],['Key priorities','top_issue'],['Action items','decide'],['Calculation basis','production_note']].map(([label,key])=>`<section class="brief-card"><h2>${label}</h2>${sectionBody(key,report[key])}<details><summary>View supporting records</summary>${report.sections[key].evidence.map(ref=>`<h3>${esc(ref)}</h3><pre>${esc(JSON.stringify(report.facts[ref],null,2))}</pre>`).join('')}</details></section>`).join('')}</div><section class="brief-card"><h2>Snapshot facts</h2><p>In progress: ${report.facts.counts.in_progress} · Overdue: ${report.facts.counts.overdue} · High risk: ${report.facts.counts.high} · Medium risk: ${report.facts.counts.medium}</p><p>Yesterday’s stage completions: ${report.facts.yesterday.records_available?report.facts.yesterday.stage_completions+' (across stages, not finished garments)':'No records available; actual output is unknown'}</p></section>`;
 }
 async function load(){
  data=await request('/api/morning');
  render();$('#status').textContent=data.model_configured?'':'Configure the model before generating a briefing.';
 }
 $('#reload').onclick=()=>load().catch(e=>$('#status').textContent=e.message);
 $('#generate').onclick=async()=>{
  if(generating)return;generating=true;$('#generate').disabled=true;$('#status').textContent='Reading the snapshot and generating your briefing…';
  try{const r=await request('/api/morning/generate',{method:'POST'});selected=r.report.id;await load();$('#status').textContent=r.status==='already_saved'?'Loaded the saved briefing for this snapshot.':'Briefing generated and saved.'}
  catch(e){$('#status').textContent=e.message+' No new report was generated. The previous report is preserved.'}
  finally{generating=false;$('#generate').disabled=false}
 };
 $('#new-chat').onclick=()=>{session=null;$('#chat-log').replaceChildren()};
 $('#chat-form').onsubmit=async e=>{
  e.preventDefault();const question=$('#question').value.trim();if(!question)return;
  const button=e.target.querySelector('button');button.disabled=true;
  try{const r=await request('/api/v1/workflow/chat',{method:'POST',body:JSON.stringify({message:question,session_id:session})});session=r.state.session_id;
   const p=document.createElement('p');p.textContent='You: '+question+'\n\nThreadPilot: '+r.answer;$('#chat-log').append(p);$('#question').value='';
   if(r.state.review_draft_id){const a=document.createElement('a');a.href='/#/risk';a.textContent='Open the review draft on the Risk page';$('#chat-log').append(a)}
  }catch(error){$('#status').textContent=error.message}finally{button.disabled=false}
 };
 load().catch(e=>$('#status').textContent=e.message+' Check your connection and try again.');
})();
