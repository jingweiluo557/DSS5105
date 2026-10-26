/* Shared workflow chat UI. Transport is implemented in ai-stream.js. */
const API_BASE = window.THREADPILOT_API_BASE;
let aiBusy=false, aiGeneration=0, aiController=null, apiLabel='Checking AI backend…';
try { const history=JSON.parse(sessionStorage.getItem('threadpilot-llm-chat')||'{}');state.chat=history.chat||[];state.chatIds=history.ids||[]; } catch {state.chat=[];state.chatIds=[];}
function persistAI(){try{sessionStorage.setItem('threadpilot-llm-chat',JSON.stringify({chat:state.chat,ids:state.chatIds}))}catch{}save()}
// Hide the backend's duplicate citation line in display only; keep raw answers for export.
function answerConditions(text){const conditions=[];String(text??'').replace(/[（(]\s*(?:假设|假定|assuming\b|assumptions?\s*:)\s*([^()（）\r\n]*)[）)]/gi,(_,value)=>{conditions.push(value.trim());return ''});return conditions}
function displayAnswer(text){return window.formatWorkspaceText(text).replace(/[（(]\s*(?:假设|假定|assuming\b|assumptions?\s*:)\s*[^()（）\r\n]*[）)]/gi,'').replace(/\r?\n\r?\nSource evidence:[^\r\n]*(?:\r?\n|$)/g,'\n\n').replace(/(?:^|\n)As of [^\n]*/g,'').replace(/[ \t]+([，。；,.])/g,'$1')}
// Answers may carry light markdown (**order IDs**, numbered or dashed lists). Escape first, then shape; no raw HTML passes.
function renderAnswer(text){
 const inline=line=>esc(line).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>');
 const blocks=String(text??'').replace(/\r\n/g,'\n').split(/\n{2,}/).map(b=>b.trim()).filter(Boolean);
 return blocks.map(block=>{
  const lines=block.split('\n');
  if(lines.every(l=>/^\s*(?:[-*•]|\d+[.)])\s+/.test(l))){const ordered=/^\s*\d+[.)]/.test(lines[0]);return `<${ordered?'ol':'ul'}>${lines.map(l=>`<li>${inline(l.replace(/^\s*(?:[-*•]|\d+[.)])\s+/,''))}</li>`).join('')}</${ordered?'ol':'ul'}>`}
  const items=[],out=[];
  for(const l of lines){if(/^\s*(?:[-*•]|\d+[.)])\s+/.test(l))items.push(l);else{if(items.length){out.push(`<ul>${items.map(x=>`<li>${inline(x.replace(/^\s*(?:[-*•]|\d+[.)])\s+/,''))}</li>`).join('')}</ul>`);items.length=0}out.push(inline(l))}}
  if(items.length)out.push(`<ul>${items.map(x=>`<li>${inline(x.replace(/^\s*(?:[-*•]|\d+[.)])\s+/,''))}</li>`).join('')}</ul>`);
  return `<p>${out.join('<br>').replace(/<br>(<ul>)/g,'$1').replace(/(<\/ul>)<br>/g,'$1')}</p>`;
 }).join('');
}
function sourceSummary(m){
 const counts={};for(const e of (m.evidence||[]))counts[e.source]=(counts[e.source]||0)+1;
 const parts=Object.entries(counts).map(([s,n])=>`${n} row${n===1?'':'s'} from ${s}`);
 const when=(m.sourceDetails||'').match(/As of ([^;]+)/);
 return (parts.length?parts.join(', '):'current records')+(when?' · as of '+formatWorkspaceTime(when[1].trim()):'');
}
const sourceAiPage=aiPage, sourceShell=shell;
shell=function(content){return sourceShell(content).replace('AI and delivery are local simulations','AI via FastAPI / OpenAI · delivery remains simulated')};
 aiPage=function(){return sourceAiPage().replace('Answers are calculated locally from your CSVs. No language-model service is connected.','Ask general questions or explore current factory data with AI.').replace('Conversation context stays with the selected source orders.','Switch topics, return to earlier questions, or ask for several things together.')};
composer=function(){return `<form class="composer" data-form="chat"><textarea aria-label="Ask ThreadPilot" name="visible-question" placeholder="Ask about an order, a risk, or your next move…" required maxlength="1500" ${aiBusy?'disabled':''}></textarea><div class="actions"><small>Context · ${esc(state.selected||'General')}<br><span class="api-status">${esc(apiLabel)}</span></small><div class="actions">${btn('voice','♩','','aria-label="Voice input"')}<button class="primary" type="submit" ${aiBusy?'disabled':''}>${aiBusy?'Thinking…':'Send ↗'}</button></div></div></form>`};
chatHTML=function(){return state.chat.map(m=>m.role==='user'?`<div class="bubble user">${esc(m.text)}</div>`:m.role==='error'?`<div class="bubble"><p>${esc(m.question)}</p><p class="error" role="alert">${esc(m.text)}</p>${btn('retry-ai','Retry')}${m.requestId?`<p><small>Request ${esc(m.requestId)}</small></p>`:''}</div>`:`<div class="bubble"><div class="eyebrow">ThreadPilot</div><div class="note md">${renderAnswer(displayAnswer(m.text))}</div>${m.facts&&m.facts.trim()&&m.facts.trim()!==String(m.text).trim()?`<details class="source-details facts"><summary>Facts from the records (before the summary)</summary><div class="md">${renderAnswer(displayAnswer(m.facts))}</div></details>`:''}${m.sourceDetails||m.evidence?.length?`<details class="source-details"><summary>Sources · ${esc(sourceSummary(m))}</summary>${(()=>{const rows=(m.evidence||[]).filter(e=>/^\/api\/(?:v1\/)?evidence\//.test(e.url));return rows.slice(0,12).map(e=>`<a href="${esc(API_BASE+e.url)}" target="_blank" rel="noopener">${esc(e.source)} ${e.row}</a>`).join(' · ')+(rows.length>12?` · and ${rows.length-12} more`:'')})()}</details>`:''}${m===state.chat.findLast(x=>x.role==='assistant')&&m.chaseDrafts?.some(d=>!d.sent)?`<div class="actions spaced">${m.chaseDrafts.filter(d=>!d.sent).map(d=>`<button type="button" data-review-chase="${d.number}">Review draft ${d.number}</button>`).join('')}</div>`:''}${m.confirmation&&m.confirmation===workflowConfirmation?`<div class="actions spaced"><button type="button" data-confirm-chase="${esc(m.confirmation)}">Confirm send</button></div>`:''}${answerConditions(m.text).length?`<details><summary>Calculation details</summary><p>${esc(answerConditions(m.text).join("；"))}</p></details>`:""}${m.ids?.length?`${m.chaseDraft||m.ids.length>2?`<details class="source-details"><summary>Related orders (${m.ids.length})</summary>`:''}<div class="ai-cards">${m.ids.filter(find).map(id=>{const o=find(id);return `<div class="ai-order"><strong>${o.id} · ${esc(o.customer)}</strong><p class="muted">${titleCase(o.stage)} · ${dueLabel(o)}</p>${riskBadge(o)}<div class="actions">${link('order','View order',id,'button small-button')}${link('evidence','Evidence',id,'button small-button')}</div></div>`}).join('')}</div>${m.chaseDraft||m.ids.length>2?'</details>':''}`:''}${m.order&&find(m.order)?`<div class="actions">${link('evidence','View evidence',m.order)}${find(m.order).status==='In progress'?link('draft','Draft chase-up',m.order)+btn('watch','Create watch','',`data-id="${m.order}"`):link('order','View order',m.order)}</div>`:''}</div>`).join('')+(aiBusy?'<div class="bubble" role="status">Thinking with your source records…</div>':'')};
function redrawAI(followLatest=false){
 const panel=document.querySelector('.copilot-chat .conversation');
 const position=panel?.scrollTop||0;
 const follow=followLatest||!panel||panel.scrollHeight-panel.scrollTop-panel.clientHeight<120;
 const pageY=window.scrollY;
 if(drawerOpen)openAIDrawer();else if(route==='ai')render();
 window.scrollTo(0,pageY);
 const next=document.querySelector('.copilot-chat .conversation');
 if(next)next.scrollTop=follow?next.scrollHeight:position;
 $$('[data-form="chat"] textarea').forEach(x=>x.disabled=aiBusy);
 $$('[data-form="chat"] button[type="submit"]').forEach(x=>x.disabled=aiBusy);
}
document.addEventListener('click',e=>{const action=e.target.closest('[data-action]')?.dataset.action;if(action==='new-chat'||action==='confirm-reset'){aiGeneration++;aiController?.abort();aiBusy=false;queueMicrotask(persistAI)}if(action==='retry-ai'){const last=state.chat.findLast(m=>m.role==='error');if(last)ask(last.question)}},true);
window.threadpilotFetch(API_BASE+'/api/v1/health').then(r=>r.json()).then(h=>{apiLabel=h.configured?'Connected':'Service not configured';$$('.api-status').forEach(x=>x.textContent=apiLabel)}).catch(()=>{apiLabel='Unable to connect';$$('.api-status').forEach(x=>x.textContent=apiLabel)});
render();
