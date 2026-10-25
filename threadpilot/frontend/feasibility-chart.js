/* Capacity picture for the Feasibility result page: one stacked bar per stage (queued pieces + the new order) against
   the pieces that stage can complete before the due date on historical rates. Data comes from POST /api/feasibility/estimate,
   the same estimate_capacity tool the chat uses, so the page and the chat agree. Pure SVG, no library. */
(function(){
  const fmt=n=>Number(n).toLocaleString('en-US');
  function capacityChartSVG(chart){
    const rows=chart.rows||[];if(!rows.length)return '<p class="muted">No capacity data.</p>';
    const W=760,left=96,right=215,barH=26,gap=34,top=44,H=top+rows.length*(barH+gap)+40;
    const max=Math.max(...rows.map(r=>Math.max(r.queued_pieces+r.new_order_pieces,r.capacity_to_due||0,r.queue_capacity_to_due||0)))*1.08;
    const x=v=>left+(W-left-right)*v/max;
    let out=`<svg class="capacity-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Queued pieces plus the new order against capacity to the due date, by stage" font-size="12">`;
    out+=`<text x="${left}" y="16" fill="#74808c">Pieces to complete before ${chart.due_date} (${chart.available_workdays} working days)</text><text x="${left}" y="32" fill="#74808c">grey = already queued · blue = this order · red = over capacity · line = capacity on historical rates</text>`;
    rows.forEach((r,i)=>{
      const y=top+i*(barH+gap),q=r.queued_pieces,n=r.new_order_pieces,cap=r.capacity_to_due,over=q+n>cap;
      out+=`<text x="${left-10}" y="${y+barH/2+4}" text-anchor="end" fill="#263441" font-weight="600">${r.stage.charAt(0)+r.stage.slice(1).toLowerCase()}</text>`;
      out+=`<rect x="${x(0)}" y="${y}" width="${x(q)-x(0)}" height="${barH}" fill="#c9d1d8" rx="3"><title>${r.stage}: ${fmt(q)} pieces already queued at or before this stage</title></rect>`;
      out+=`<rect x="${x(q)}" y="${y}" width="${Math.max(2,x(q+n)-x(q))}" height="${barH}" fill="${over?'#a15c54':'#52799c'}" rx="3"><title>${r.stage}: this order adds ${fmt(n)} pieces</title></rect>`;
      if(cap){out+=`<line x1="${x(cap)}" x2="${x(cap)}" y1="${y-5}" y2="${y+barH+5}" stroke="#263441" stroke-width="2"/><text x="${x(cap)}" y="${y+barH+18}" text-anchor="middle" fill="#263441" font-size="11">capacity ${fmt(cap)}</text>`}
      if(r.queue_capacity_to_due&&Math.abs(r.queue_capacity_to_due-cap)/cap>0.05){out+=`<line x1="${x(r.queue_capacity_to_due)}" x2="${x(r.queue_capacity_to_due)}" y1="${y-2}" y2="${y+barH+2}" stroke="#74808c" stroke-dasharray="4 3"/>`}
      out+=`<text x="${Math.max(x(q+n),cap?x(cap):0)+8}" y="${y+barH/2+4}" fill="${over?'#a15c54':'#263441'}">${fmt(q+n)} · ${r.load_pct_of_capacity}% of capacity</text>`;
    });
    const yb=top+rows.length*(barH+gap)+8;
    out+=`<text x="${left}" y="${yb}" fill="#74808c" font-size="11">Dashed = queue-simulation capacity (previous eight same weekdays × completion factor) where it differs.</text>`;
    out+=`</svg>`;return out;
  }
  function verdictHTML(est,chart){
    const q=est.queue_projection,aft=est.historical_lead_time_model||{};
    const badge={likely:'watch',tight:'warning',unlikely:'severe'}[est.verdict]||'';
    return `<div class="metric-inline"><span class="badge ${badge}">${est.preliminary}</span>`+
      (q?`<span>Queue projection: best case <b>${q.best_case.finish_date||'beyond horizon'}</b>, with usual new orders <b>${q.expected_case.finish_date||'beyond horizon'}</b> · due ${est.due_date}</span>`:`<span>Queue projection unavailable: ${est.queue_projection_unavailable||''}</span>`)+
      (aft.p_on_time!=null?`<span>Orders of this size finished within the promised time <b>${Math.round(aft.p_on_time*100)}%</b> of the time (historical lead-time model; 80%-confidence date ${aft.earliest_date_80pct_confidence})</span>`:'')+
      `<span>Bottleneck stage: <b>${chart.bottleneck?chart.bottleneck.toLowerCase():'—'}</b></span></div>`;
  }
  window.loadCapacityPicture=async function(){
    const host=document.getElementById('capacity-picture');if(!host)return;
    try{
      const body={quantity:feasibility.qty,product:feasibility.category==='ACCESSORIES'?'scarf':'hoodie',due_date:feasibility.due,delivery_point:'factory'};
      const r=await window.threadpilotFetch(window.THREADPILOT_API_BASE+'/api/feasibility/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!r.ok)throw new Error('Estimate unavailable ('+r.status+')');
      const data=await r.json();
      host.innerHTML=`<div class="section-heading"><h2>Capacity picture</h2><span class="badge">Same tool as the chat · estimate_capacity</span></div>${verdictHTML(data.estimate,data.chart)}<div class="chart-wrap spaced">${capacityChartSVG(data.chart)}</div><p class="muted">${esc(data.chart.reading)} Worst case (every queued piece ahead at every stage, no overlap): ${data.estimate.worst_case_serial_backlog.scenario_required_days} working days against ${data.estimate.available_workdays} available.</p><details><summary>Assumptions</summary><ul>${(data.estimate.assumptions||[]).map(a=>`<li>${esc(a)}</li>`).join('')}</ul></details>`;
    }catch(e){host.innerHTML=`<h2>Capacity picture</h2><p class="muted">${esc(e.message)}. The local indicative model above still applies.</p>`}
  };
  window.capacityChartSVG=capacityChartSVG;window.capacityVerdictHTML=verdictHTML;
})();
