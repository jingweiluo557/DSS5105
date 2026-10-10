let predictionData=null,predictionError='',predictionLoading=false,predictionPage=1;
let predictionFilters={query:'',risk:'',stage:'',category:'',delivery:''};
function predictionRows(){
 let rows=(predictionData?.rows||[]).filter(r=>(r.order_id+' '+r.customer+' '+r.product).toLowerCase().includes(predictionFilters.query.toLowerCase())&&
  (!predictionFilters.risk||r.risk_level===predictionFilters.risk)&&(!predictionFilters.stage||r.current_stage===predictionFilters.stage)&&
  (!predictionFilters.category||r.category===predictionFilters.category)&&(!predictionFilters.delivery||(predictionFilters.delivery==='late'?r.due_date<predictionData.business_date:r.due_date>=predictionData.business_date)));
 rows.sort((a,b)=>b.delay_probability-a.delay_probability||a.due_date.localeCompare(b.due_date)||a.order_id.localeCompare(b.order_id));
 const pages=Math.max(1,Math.ceil(rows.length/15));predictionPage=Math.min(predictionPage,pages);
 return `<div class="section-heading"><p class="muted">${rows.length} matching predictions · ${predictionData?.rows.length||0} imported orders</p><small>Page ${predictionPage} / ${pages}</small></div><div class="table-wrap"><table class="prediction-table"><thead><tr><th>Order / Customer</th><th>Product / Quantity</th><th>Stage / Due date</th><th>Delay risk</th><th>Estimated completion</th><th>Workshop scenario</th><th></th></tr></thead><tbody>${rows.slice((predictionPage-1)*15,predictionPage*15).map(r=>`<tr><td>${link('order',esc(r.order_id),r.order_id,'')}<br><small>${esc(r.customer)}</small></td><td>${esc(r.product)}<br><small>${Number(r.pieces).toLocaleString()} · ${esc(r.category)}</small></td><td>${titleCase(r.current_stage)}<br><small>${esc(r.due_date)}</small></td><td><strong>${(r.delay_probability*100).toFixed(1)}%</strong><br><span class="badge ${r.risk_level==='HIGH'?'severe':r.risk_level==='MEDIUM'?'warning':'watch'}">${titleCase(r.risk_level)}</span>${r.due_date<predictionData.business_date?'<br><small class="error">Already overdue</small>':''}</td><td>${esc(r.estimated_completion_date)}<br><small>Full-order scenario</small></td><td>${esc(r.workshop.name)}<br><small>${Number(r.total_estimated_days).toFixed(1)} calendar days</small></td><td>${btn('prediction-detail','View forecast','small-button',`data-id="${esc(r.order_id)}"`)}</td></tr>`).join('')||`<tr><td colspan="7">${predictionLoading?'Loading forecasts…':'No matching predictions.'}</td></tr>`}</tbody></table></div><div class="actions spaced">${btn('prediction-prev','← Previous','',predictionPage<=1?'disabled':'')}${btn('prediction-next','Next →','',predictionPage>=pages?'disabled':'')}<small>15 rows per page</small></div>`;
}
window.renderPredictions=function(){
 const rows=predictionData?.rows||[],counts=['HIGH','MEDIUM','LOW'].map(r=>rows.filter(x=>x.risk_level===r).length);
 return `<div class="predictions-page">${head('AI predictions','Order delay risk and capacity-based completion scenarios.',btn('prediction-refresh','Refresh'))}${predictionError?`<div class="callout error" role="alert">${esc(predictionError)}</div>`:''}${predictionData&&!predictionData.valid?'<div class="callout error" role="status">Archived forecast: business date or source data has changed. Refresh the model export before using these estimates.</div>':''}<div class="prediction-overview"><span class="badge">${rows.length} forecasts</span>${['High','Medium','Low'].map((label,i)=>`<span class="badge ${i===0?'severe':i===1?'warning':'watch'}">${label} · ${counts[i]}</span>`).join('')}<span class="muted">Business date ${esc(predictionData?.business_date||'—')}</span>${predictionData?.imported_at?`<small>Imported ${esc(formatWorkspaceTime(predictionData.imported_at))}</small>`:''}</div><section class="card"><form id="prediction-filters" class="filters"><label>Order / customer / product<input name="query" value="${esc(predictionFilters.query)}" placeholder="Search predictions…"></label>${[['risk','Model risk',['HIGH','MEDIUM','LOW']],['stage','Stage',stages],['category','Category',['TOPS','ACCESSORIES']],['delivery','Delivery',['late','not_late']]].map(([name,label,values])=>`<label>${label}<select name="${name}"><option value="">All</option>${values.map(v=>`<option value="${v}" ${predictionFilters[name]===v?'selected':''}>${name==='delivery'?(v==='late'?'Already overdue':'Not yet overdue'):titleCase(v)}</option>`).join('')}</select></label>`).join('')}${btn('prediction-clear','Clear')}</form><div id="prediction-results">${predictionRows()}</div></section><p class="muted prediction-note">High ≥60% · Medium 35–59.9% · Low &lt;35%. Model risk is separate from the Order center priority score.</p></div>`;
};
async function loadPredictions(){
 if(predictionLoading)return;predictionLoading=true;predictionError='';
 try{predictionData=await dashboardRequest('predictions')}catch(e){predictionError=e.message}
 finally{predictionLoading=false;if(route==='predictions')render()}
}
function updatePredictionResults(){const el=document.getElementById('prediction-results');if(el)el.innerHTML=predictionRows()}
document.addEventListener('input',e=>{if(e.target.matches('#prediction-filters input')){predictionFilters[e.target.name]=e.target.value;predictionPage=1;updatePredictionResults()}});
document.addEventListener('change',e=>{if(e.target.matches('#prediction-filters select')){predictionFilters[e.target.name]=e.target.value;predictionPage=1;updatePredictionResults()}});
document.addEventListener('submit',e=>{if(e.target.id==='prediction-filters')e.preventDefault()});
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;
 if(action==='prediction-refresh')loadPredictions();
 if(action==='prediction-prev'){predictionPage--;updatePredictionResults()}
 if(action==='prediction-next'){predictionPage++;updatePredictionResults()}
 if(action==='prediction-clear'){predictionFilters={query:'',risk:'',stage:'',category:'',delivery:''};predictionPage=1;render()}
 if(action==='prediction-detail'){
  b.disabled=true;
  try{
   const r=await dashboardRequest('predictions/'+encodeURIComponent(b.dataset.id)),c=r.completion,f=c.forecast;
   const features=r.evidence?.predict_order_delay?.data?.features||{};
   modal(`${esc(r.order_id)} · Forecast`,`${!r.valid_for_current_data?'<p class="error">Archived estimate — current inputs differ.</p>':''}<p><strong>${(r.prediction.delay_probability*100).toFixed(1)}% delay risk</strong> · ${esc(r.prediction.risk_level)} · Business date ${esc(r.business_date)}</p><div class="facts"><div><small>Quantity assumed remaining</small><strong>${Number(c.remaining_pieces).toLocaleString()}</strong></div><div><small>Workshop</small><strong>${esc(c.workshop.name)}</strong></div><div><small>Estimated completion</small><strong>${esc(f.estimated_completion_date)}</strong></div></div><h3>Completion estimate</h3><p>${Number(f.production_days).toFixed(2)} production days + ${f.queue_days} queue days + ${f.pickup_days} pickup days = ${Number(f.total_estimated_days).toFixed(2)} calendar days.</p><p class="muted">Assumes the full order remains and workshop capacity is available exclusively. Calendar-day rounding in the supplied export is retained; verify the schedule before making a commitment.</p><h3>Model inputs</h3><p>Planned lead time: ${esc(features.planned_lead_days??'—')} days · Quantity: ${esc(features.pieces??'—')} · Factory output trend: ${features.factory_output_trend==null?'—':(features.factory_output_trend*100).toFixed(1)+'%'}</p><div class="actions"><a class="button" href="${esc(window.THREADPILOT_API_BASE)}/api/predictions/${esc(r.order_id)}">View source data</a>${link('order','Open order',r.order_id)}</div>`,'close','Done');
  }catch(error){toast(error.message)}finally{b.disabled=false}
 }
});
window.addEventListener('hashchange',()=>{if(route==='predictions')loadPredictions()});
render();if(route==='predictions')loadPredictions();
