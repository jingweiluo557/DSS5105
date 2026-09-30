/* Presentation only: the workflow transport and session lifecycle stay in ai-stream.js. */
const workspaceTools = [['ai','Conversation'],['orders','Orders'],['exceptions','Exceptions'],['risk','Risk orders'],['feasibility','Feasibility'],['messages','Watches & receipts']];
nav.splice(0, nav.length, ['dashboard','◫','Dashboard'], ['ai','✧','AI workspace'], ['activity','◷','Activity Log'], ['settings','⚙','Settings']);
const workspaceShell = shell;
shell = function(content) {
  const inWorkspace = !['dashboard','activity','settings'].includes(route);
  const active = {order:'orders',evidence:'orders',draft:'messages',result:'feasibility'}[route] || route;
  const tools = inWorkspace ? `<nav class="workspace-tools" aria-label="Workspace tools">${workspaceTools.map(([r,label])=>`<a href="#/${r}" ${active===r?'aria-current="page"':''}>${label}</a>`).join('')}</nav>` : '';
  let html = workspaceShell(tools + content);
  if (inWorkspace) html = html.replace('href="#/ai" class=""', 'href="#/ai" class="active" aria-current="page"');
  html = html.replace(/<div class="demo-banner">.*?<\/div>/, `<div class="demo-banner">Business date ${esc(TODAY)} · ${orders.length} orders · Database snapshot with live AI analysis</div>`)
    .replace('LOCAL DEMO','WORKSPACE');
  if (route === 'ai') html = html.replace('class="page"','class="page workspace-page"').replace(/<button class="primary floating"[^>]*>.*?<\/button>/,'');
  return html;
};

function workspaceEvidence() {
  const answers = state.chat.filter(m=>m.role==='assistant');
  return answers.map((m,index)=>{
    const records=(m.evidence||[]).filter(e=>/^\/api\/evidence\/(orders|production_log|workshops)\/\d+$/.test(e.url));
    return `<details ${index===answers.length-1?'open':''}><summary>Answer ${index+1} · ${records.length} records</summary><p class="muted">${esc(m.businessDate||TODAY)} · ${esc(m.source||'No source cited')}</p>${records.map(e=>`<a class="evidence-record" href="${API_BASE+e.url}" target="_blank" rel="noopener"><span>${esc(e.source)}</span><strong>Record ${esc(e.row)} ↗</strong></a>`).join('')||'<p class="muted">No database evidence links returned for this answer.</p>'}${m.requestId?`<small>Request ${esc(m.requestId)}</small>`:''}</details>`;
  }).reverse().join('') || '<p class="muted">Verified database records will appear here when an answer is complete.</p>';
}

aiPage = function() {
  const turns=state.chat.filter(m=>m.role==='user');
  return `<section class="copilot-workspace" aria-label="AI workspace">
    <header class="workspace-heading"><div><div class="eyebrow">THREADPILOT / CO-PILOT</div><h1>One place. A clearer day.</h1><p class="muted">Briefing, conversation and the evidence behind each decision.</p></div>${btn('new-chat','New conversation')}</header>
    <div class="copilot-columns">
      <aside class="copilot-context" aria-label="Briefing and conversation history">
        <section class="workspace-panel"><div class="section-heading"><h2>Morning briefing</h2><span class="badge">${esc(TODAY)}</span></div><p class="muted">Current page snapshot</p><div class="brief-metrics"><a href="#/orders?due=Overdue"><strong>${overdue.length}</strong>Overdue</a><a href="#/orders?idle=5"><strong>${idleOrders.length}</strong>Idle ≥5 days</a></div><p><strong>${esc(titleCase(worstStage.stage))}</strong> output: ${Number(worstStage.latest.pieces_completed).toLocaleString()} pieces on ${esc(worstStage.latest.date)}.</p>${btn('suggest','Generate daily report ↗','primary', 'data-question="Give me a daily briefing of overdue orders, production bottlenecks and recommended follow-ups." '+(aiBusy?'disabled':''))}<p class="muted spaced">The report continues this conversation using current backend records.</p></section>
        <section class="workspace-panel"><div class="section-heading"><h2>Conversation record</h2><span class="badge">${turns.length} turns</span></div><p class="muted">Current session · saved in this browser tab</p><ol class="turn-list">${turns.map((m,i)=>`<li>${btn('jump-turn',esc(m.text),'turn-link',`data-turn="${i}"`)}</li>`).join('')||'<li class="muted">Your questions will appear here.</li>'}</ol>${btn('export-conversation','Export conversation','small-button',state.chat.length?'':'disabled')}</section>
      </aside>
      <section class="copilot-chat" aria-label="Conversation"><div class="chat-heading"><strong>✧ AI Co-Pilot</strong><span class="badge ${aiBusy?'warning':'watch'}">${aiBusy?'Working…':'Ready for your question'}</span></div><div class="conversation">${chatHTML()||'<div class="chat-welcome"><span class="ai-emblem">✧</span><h2>What needs your attention?</h2><p class="muted">Ask a question, inspect the records, then continue with a follow-up.</p></div>'}</div><div class="workspace-suggestions">${['Which orders are most at risk?','Only show TrendCart orders.','How was assembly output yesterday?'].map(q=>btn('suggest',esc(q),'small-button',`data-question="${esc(q)}" ${aiBusy?'disabled':''}`)).join('')}</div>${composer()}</section>
      <aside class="copilot-evidence" aria-label="Evidence and actions"><section class="workspace-panel"><div class="eyebrow">SOURCE RECORDS</div><h2>Actual evidence</h2>${workspaceEvidence()}</section><section class="workspace-panel"><h2>Follow up</h2><p class="muted">Review notes, chase-ups and standing reminders in this conversation. Confirm an action after reviewing its preview.</p><div class="actions">${link('messages','Watches & receipts')}${link('activity','Local activity log')}${link('feasibility','Assess a new order')}</div><details><summary>Local tools</summary><p class="muted">Manual watches, receipts and saved scenarios remain available in the tools above. Simulated receipts do not send external messages.</p></details></section></aside>
    </div></section>`;
};

// All Ask AI entry points lead to the same conversation surface.
openAIDrawer = function() { closeOverlay(); if(route!=='ai')go('ai'); else document.querySelector('[name="visible-question"]')?.focus(); };
document.addEventListener('click', e=>{
  const button=e.target.closest('[data-action]');
  if(button?.dataset.action==='jump-turn') {
    const target=document.querySelectorAll('.copilot-chat .bubble.user')[Number(button.dataset.turn)];
    target?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'center'});
  }
  if(button?.dataset.action==='export-conversation')download('threadpilot-conversation.json',{business_date:TODAY,messages:state.chat});
});
render();
