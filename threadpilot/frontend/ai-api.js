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
// How an answer was made. While the answer is being made, one line says what is happening right now, in plain words;
// afterwards the same line says what was done. "Show more" opens every step: memory, the planner's reading, each tool
// call with its inputs, result, source rows and time, then the narration.
const TOOL_WORDS={search_orders:'Finding the matching orders',refresh_order:'Looking up the order record',assess_order_risk:'Checking delivery risk in the queue',assess_expedite:'Testing what moving it forward would do to the queue',compare_orders:'Comparing the orders',rank_comparison:'Ranking the compared orders',estimate_capacity:'Running the new order through the queue',predict_order_delay:'Estimating the on-time chance',prioritize_orders:'Ranking what needs attention',rank_active_orders:'Ranking the active orders',summarize_orders:'Counting the order book',check_normality:'Comparing with the previous eight same weekdays',explain_deviation:'Reading the production records around the drop',get_production_output:'Reading the production log',find_anomalies:'Scanning yesterday for anything unusual',list_workshops:'Checking the outside workshops',draft_chase:'Drafting the chase-up',send_chase:'Sending the email from your Outlook',save_internal_note:'Saving the note on the order',upsert_reminder:'Setting the reminder',recall_conversation:'Recalling this conversation',explain_baseline_choice:'Fetching the baseline study',explain_no_data:'Checking what the records can answer',generate_morning_briefing:'Writing the morning briefing',review_reason_draft:'Drafting the review reason'};
const INTENT_WORDS={'order.lookup':'an order look-up','order.refresh':'an order check','order.risk':'a delivery-risk question','order.risk_overview':'a risk overview','order.summary':'an order-book question','order.compare':'a comparison','order.commitment':'a feasibility question','order.prioritize':'a what-needs-attention question','order.expedite':'an expedite check','order.rank':'a ranking','order.forecast':'a forecast','operations.normality':'a normal-range check','operations.deviation':'a why-was-output-low question','operations.output':'a production-output question','operations.discovery':'a what-went-wrong question','operations.briefing':'a briefing request','data.workshops':'a workshop question','execution.chase':'a chase-up request','execution.note':'a note to save','execution.reminder':'a reminder to set','general.unanswerable':'something the records cannot answer','review.reason':'a review reason','unknown':'unclear'};
function stepWords(s){
 if(s.phase==='memory')return 'Recalling '+s.text;
 if(s.phase==='plan')return s.slots?`Reading it as ${INTENT_WORDS[s.text]||s.text}${s.slots.order_ids?' for '+s.slots.order_ids:s.slots.customer?' for '+s.slots.customer:s.slots.stage?' for '+String(s.slots.stage).toLowerCase():''}`:s.text;
 if(s.phase==='tool'){const o=s.arguments?.order_id||s.arguments?.order_ids;return (TOOL_WORDS[s.text]||'Running '+s.text)+(o?' · '+o:'')}
 return s.text;
}
function stepDetail(s){
 const args=s.arguments&&Object.keys(s.arguments).length?' <span class="muted">'+esc(Object.entries(s.arguments).map(([k,v])=>k+': '+v).join(' · '))+'</span>':'';
 if(s.phase==='memory')return `${esc(stepWords(s))} <span class="muted">(${esc(s.source||'this conversation')}) · <code>recall_conversation</code></span>`;
 if(s.phase==='plan'&&s.slots)return `${esc(stepWords(s))} <span class="muted">· planner <code>${esc(s.text)}</code>${Object.keys(s.slots).length?' · '+esc(Object.entries(s.slots).map(([k,v])=>k+' '+v).join(' · ')):''}${s.confidence!=null?` · confidence ${s.confidence}`:''}${s.ms!=null?` · ${s.ms} ms`:''}</span>`;
 if(s.phase==='tool')return `${esc(stepWords(s))} <span class="muted">· <code>${esc(s.text)}</code></span>${args}${s.summary?' <span class="muted">→</span> '+esc(s.summary):''}${s.rows?` <span class="muted">· ${s.rows} source row${s.rows===1?'':'s'}</span>`:''}${s.ms!=null?` <span class="muted">· ${s.ms} ms</span>`:''}${s.executed===false?' <span class="muted">· nothing executed</span>':''}`;
 return esc(s.text)+(s.model?` <span class="muted">(${esc(s.model)})</span>`:'');
}
let aiStepsOpen=false;
document.addEventListener('toggle',e=>{if(e.target.matches?.('details.tool-steps.live'))aiStepsOpen=e.target.open},true);
function stepsHTML(steps,live){
 if(!steps?.length)return '';
 const items=steps.map((s,i)=>`<li class="${live&&i===steps.length-1?'running':'done'} step-${esc(s.phase||'')}">${stepDetail(s)}</li>`).join('');
 const tools=steps.filter(s=>s.phase==='tool'),rows=tools.map(s=>s.rows).find(r=>r),ms=steps.reduce((t,s)=>t+(s.ms||0),0);
 const now=live?esc(stepWords(steps[steps.length-1]))+'…':`${tools.length?`${tools.length} tool call${tools.length===1?'':'s'}`:'No tool calls'}${rows?` · ${rows} source row${rows===1?'':'s'}`:''}${steps.some(s=>s.phase==='memory')?' · memory used':''}${ms?` · ${ms>=1000?(ms/1000).toFixed(1)+' s':Math.round(ms)+' ms'}`:''}`;
 return `<details class="tool-steps${live?' live':''}"${live&&aiStepsOpen?' open':''}><summary><span class="tp-dot" aria-hidden="true"></span><span class="tp-now" ${live?'aria-live="polite"':''}>${now}</span><span class="tp-more"></span></summary><ol>${items}</ol></details>`;
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
chatHTML=function(){return state.chat.map(m=>m.role==='user'?`<div class="bubble user">${esc(m.text)}</div>`:m.role==='error'?`<div class="bubble"><p>${esc(m.question)}</p><p class="error" role="alert">${esc(m.text)}</p>${btn('retry-ai','Retry')}${m.requestId?`<p><small>Request ${esc(m.requestId)}</small></p>`:''}</div>`:`<div class="bubble"><div class="eyebrow">ThreadPilot</div><div class="note md">${renderAnswer(displayAnswer(m.text))}</div>${stepsHTML(m.steps,false)}${/previous eight same weekdays/i.test(m.text)&&!m.steps?.some(s=>s.text==='explain_baseline_choice')?whyEightHTML():''}${m.facts&&m.facts.trim()&&m.facts.trim()!==String(m.text).trim()?`<details class="source-details facts"><summary>Facts from the records (before the summary)</summary><div class="md">${renderAnswer(displayAnswer(m.facts))}</div></details>`:''}${m.sourceDetails||m.evidence?.length?`<details class="source-details"><summary>Sources · ${esc(sourceSummary(m))}</summary>${(()=>{const rows=(m.evidence||[]).filter(e=>/^\/api\/(?:v1\/)?evidence\//.test(e.url));return rows.slice(0,12).map(e=>`<a href="${esc(API_BASE+e.url)}" target="_blank" rel="noopener">${esc(e.source)} ${e.row}</a>`).join(' · ')+(rows.length>12?` · and ${rows.length-12} more`:'')})()}</details>`:''}${m===state.chat.findLast(x=>x.role==='assistant')&&m.chaseDrafts?.some(d=>!d.sent)?`<div class="actions spaced">${m.chaseDrafts.filter(d=>!d.sent).map(d=>`<button type="button" data-review-chase="${d.number}">Review draft ${d.number}</button>`).join('')}</div>`:''}${m.confirmation&&m.confirmation===workflowConfirmation?`<div class="actions spaced"><button type="button" data-confirm-chase="${esc(m.confirmation)}">Confirm send</button></div>`:''}${answerConditions(m.text).length?`<details><summary>Calculation details</summary><p>${esc(answerConditions(m.text).join("；"))}</p></details>`:""}${m.ids?.length?`${m.chaseDraft||m.ids.length>2?`<details class="source-details"><summary>Related orders (${m.ids.length})</summary>`:''}<div class="ai-cards">${m.ids.filter(find).map(id=>{const o=find(id);return `<div class="ai-order"><strong>${o.id} · ${esc(o.customer)}</strong><p class="muted">${titleCase(o.stage)} · ${dueLabel(o)}</p>${riskBadge(o)}<div class="actions">${link('order','View order',id,'button small-button')}${link('evidence','Evidence',id,'button small-button')}</div></div>`}).join('')}</div>${m.chaseDraft||m.ids.length>2?'</details>':''}`:''}${m.order&&find(m.order)?`<div class="actions">${link('evidence','View evidence',m.order)}${find(m.order).status==='In progress'?link('draft','Draft chase-up',m.order)+btn('watch','Create watch','',`data-id="${m.order}"`):link('order','View order',m.order)}</div>`:''}</div>`).join('')+(aiBusy?'<div class="bubble" role="status">Thinking with your source records…</div>':'')};
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
