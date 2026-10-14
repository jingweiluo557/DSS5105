/* Current backend contract only: no embedded simulation dataset or legacy /chat payload. */
(() => {
 const $=s=>document.querySelector(s),base=window.THREADPILOT_API_BASE;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let data=null,session=null,selected=null,generating=false;
 $('#connection').textContent='连接后端：'+base;
 async function request(path,options={}){
  if(window.THREADPILOT_CONFIG_ERROR)throw Error(window.THREADPILOT_CONFIG_ERROR);
  const r=await window.threadpilotFetch(base+path,{...options,cache:'no-store',headers:{'Content-Type':'application/json'}});
  const body=await r.json();if(!r.ok)throw Error(body.error?.message||body.detail||'无法连接后端');return body;
 }
 function render(){
  const report=data.reports.find(r=>r.id===selected)||data.reports[0];
  if(!report){$('#report').innerHTML='<section class="brief-card">尚无模型晨报。点击生成后，将使用数据库事实调用已配置的大模型。</section>';return}
  selected=report.id;$('#report-select').value=selected;
  const stale=report.fingerprint!==data.current_fingerprint;
  $('#report').innerHTML=`<section class="brief-card"><strong>模型：${esc(report.model)}</strong><p>业务日期：${esc(report.business_date)} · 生成时间：${esc(report.generated_at)}<br>最新生产记录：${esc(report.latest_production_date||'暂无')}</p>${report.generation_version!=='morning-v4'?'<p>此报告由旧版分析规则生成，请重新生成以使用当前事实核对规则。</p>':''}${stale?'<p>此报告基于较早快照；可生成当前数据的报告。历史报告保持原样。</p>':''}<p>记录编号：${esc(report.id.slice(0,12))}</p></section><div class="brief-grid">${[['生产回顾','yesterday'],['优先问题','top_issue'],['经理决策','decide'],['产能假设与限制（系统计算口径）','production_note']].map(([label,key])=>`<section class="brief-card"><h2>${label}</h2><p>${esc(report[key])}</p><details><summary>查看数据库依据</summary>${report.sections[key].evidence.map(ref=>`<h3>${esc(ref)}</h3><pre>${esc(JSON.stringify(report.facts[ref],null,2))}</pre>`).join('')}</details></section>`).join('')}</div><section class="brief-card"><h2>事实快照</h2><p>在制 ${report.facts.counts.in_progress} 单 · 已逾期 ${report.facts.counts.overdue} 单 · 高风险 ${report.facts.counts.high} 单 · 中风险 ${report.facts.counts.medium} 单</p><p>昨日工序完成量：${report.facts.yesterday.records_available?report.facts.yesterday.stage_completions+'（跨工序累计，不等于成衣完成量）':'无记录，不能推断实际产量为零'}</p></section>`;
 }
 async function load(){
  data=await request('/api/morning');$('#report-select').innerHTML=data.reports.map(r=>`<option value="${esc(r.id)}">${esc(r.generated_at)} · 业务日 ${esc(r.business_date)}</option>`).join('');
  render();$('#status').textContent=data.model_configured?'已连接。生成会调用真实模型，相同快照复用已有报告。':'模型尚未配置；不能生成 AI 晨报。';
 }
 $('#report-select').onchange=e=>{selected=e.target.value;render()};
 $('#reload').onclick=()=>load().catch(e=>$('#status').textContent=e.message);
 $('#generate').onclick=async()=>{
  if(generating)return;generating=true;$('#generate').disabled=true;$('#status').textContent='正在读取数据库并调用模型分析…';
  try{const r=await request('/api/morning/generate',{method:'POST'});selected=r.report.id;await load();$('#status').textContent=r.status==='already_saved'?'已载入相同快照的模型报告。':'真实模型晨报已生成并保存。'}
  catch(e){$('#status').textContent=e.message+' 未生成模拟晨报，原报告保留。'}
  finally{generating=false;$('#generate').disabled=false}
 };
 $('#new-chat').onclick=()=>{session=null;$('#chat-log').replaceChildren()};
 $('#chat-form').onsubmit=async e=>{
  e.preventDefault();const question=$('#question').value.trim();if(!question)return;
  const button=e.target.querySelector('button');button.disabled=true;
  try{const r=await request('/api/v1/workflow/chat',{method:'POST',body:JSON.stringify({message:question,session_id:session})});session=r.state.session_id;
   const p=document.createElement('p');p.textContent='你：'+question+'\n\nThreadPilot：'+r.answer;$('#chat-log').append(p);$('#question').value='';
   if(r.state.review_draft_id){const a=document.createElement('a');a.href='/#/risk';a.textContent='在风险页面打开该订单的审核草稿';$('#chat-log').append(a)}
  }catch(error){$('#status').textContent=error.message}finally{button.disabled=false}
 };
 load().catch(e=>$('#status').textContent=e.message+' 请检查显示的后端地址，页面不会自动切换到其他服务器。');
})();
