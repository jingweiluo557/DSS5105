/* Owner email preferences and server-backed delivery history. */
(() => {
  let model = null, loading = false;
  const labels = {scheduled:'Scheduled',accepted:'Accepted by Microsoft',rejected:'Rejected',unknown:'Check Sent Items',submitting:'Submission pending',sending:'Sending',generating:'Preparing briefing',generation_failed:'Briefing unavailable',needs_attention:'Connection needs attention',cancelled:'Cancelled'};
  const action = (name, text, primary=false) => `<button type="button" data-email="${name}" class="${primary?'primary':''}">${text}</button>`;
  async function api(path, method='GET', body) {
    const r = await window.threadpilotFetch(window.THREADPILOT_API_BASE+'/api/'+path,{method,cache:'no-store',headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-Confirm-Write':'true'}:{})},...(body?{body:JSON.stringify(body)}:{})});
    const data=await r.json();
    if(!r.ok)throw new Error(r.status===401?'Connect to your workspace to continue.':data.error?.message||(typeof data.detail==='string'?data.detail:'Check the email addresses and required fields.'));
    return data;
  }
  const contact = (c={}) => `<div class="email-contact"><label class="field">Customer<input name="customer" value="${esc(c.customer||'')}" maxlength="160" required></label><label class="field">Contact name<input name="name" value="${esc(c.name||'')}" maxlength="160"></label><label class="field">Email<input name="email" type="email" value="${esc(c.email||'')}" maxlength="254" required></label>${action('remove-contact','Remove')}</div>`;
  function clockForm(){
    const c=model.clock;
    const local=new Date(Date.parse(c.now)+8*3600000).toISOString().slice(0,16);
    return `<section class="card business-clock-card"><div class="eyebrow">DEMO</div><h2>Business clock</h2><p class="muted">For demonstrations only: moves the business date the whole workspace uses.</p><p><strong id="business-clock-live"></strong></p><form id="business-clock-form"><label class="field">Date and time<input name="business_time" type="datetime-local" value="${local}"></label><div class="actions"><button class="primary" type="submit" value="demo">Start demo clock</button><button type="submit" value="live">Use real time</button></div></form></section>`;
  }
  setInterval(()=>{const el=document.getElementById('business-clock-live');if(el&&window.threadpilotNow)el.textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(window.threadpilotNow());},1000);
  function content() {
    const p=model.preferences,c=model.connection;
    return `<div class="grid equal email-top"><section class="card ${p.briefing_enabled?'':'attention'}"><div class="eyebrow">DAILY BRIEFING</div><div class="email-time">07:00 <small>every morning</small></div><span class="badge ${p.briefing_enabled?'ok':'severe'}">${p.briefing_enabled?'On':'Paused — nothing is sent'}</span><p>${p.briefing_enabled?'Scheduled from '+esc(model.clock?.schedule_start_day||p.start_day)+' · sent to '+esc(p.manager_email):'Tick “send the daily briefing” below and save to start delivery.'}</p><a href="#/activity">View delivery activity →</a></section><section class="card"><div class="eyebrow">MAILBOX CONNECTION</div><h2>Send from Outlook</h2><span class="badge ${c.connected?'ok':'watch'}">${c.connected?'Connected':'Not connected'}</span><p class="email-address">${esc(c.account||'Connect your personal Outlook account')}</p><p>ThreadPilot sends through this mailbox. Your Microsoft password stays with Microsoft.</p><div class="actions">${action('connect',c.connected?'Reconnect Outlook':'Connect Outlook',true)}${c.connected?action('disconnect','Disconnect'):''}</div></section></div>
      ${alertsCard()}
      <form id="email-preferences"><section class="card"><div class="eyebrow">MORNING BRIEFING</div><h2>Manager delivery preferences</h2><div class="grid equal"><label class="field">Manager name<input name="manager_name" value="${esc(p.manager_name)}" maxlength="100"></label><label class="field">Manager recipient email<input name="manager_email" type="email" required maxlength="254" value="${esc(p.manager_email)}"></label></div><label class="field">Email subject prefix<input name="subject_prefix" required maxlength="120" value="${esc(p.subject_prefix)}"></label><label class="field field-inline"><input name="briefing_enabled" type="checkbox" ${p.briefing_enabled?'checked':''}>Send the daily briefing at 07:00 (Asia/Shanghai, UTC+08:00)</label><label class="field field-inline"><input name="alert_emails_enabled" type="checkbox" ${p.alert_emails_enabled?'checked':''}>Email me at once when something needs me today: a stage far outside its normal range, three days below it, an order that will miss, a customer whose orders all stopped (at most 3 a day; everything else waits for the briefing)</label></section>
      <section class="card"><div class="eyebrow">ORDER FOLLOW-UP</div><h2>Department emails</h2><div class="grid equal">${['KNITTING','ASSEMBLY','WASHING','PACKING'].map(d=>`<label class="field">${d.charAt(0)+d.slice(1).toLowerCase()}<input name="department_${d}" type="email" maxlength="254" value="${esc((p.departments||{})[d]||'')}" placeholder="Department email"></label>`).join('')}</div></section>
      <section class="card"><div class="section-heading"><div><div class="eyebrow">CUSTOMER ADDRESS BOOK</div><h2>Customer emails</h2></div>${action('add-contact','Add customer')}</div><div id="email-contacts">${p.customers.map(contact).join('')}</div><p id="contacts-empty" ${p.customers.length?'hidden':''}>No customer contacts saved yet.</p></section><div class="actions"><button class="primary" type="submit">Save email settings</button>${action('reload','Discard changes')}</div></form>`+clockForm();
  }
  // Alert emails: on/off, what would be emailed right now, and a test send (the policy itself: docs/ALERT_POLICY.md)
  function alertsCard(){
    const p=model.preferences,a=model.alerts,on=a?a.emails_enabled:p.alert_emails_enabled;
    const now=(a?.email_now||[]),digest=(a?.digest||[]).length,watch=(a?.briefing_only||[]).length;
    return `<section class="card ${on?'':'attention'}"><div class="section-heading"><div><div class="eyebrow">ALERT EMAILS</div><h2>Interrupt me only when it matters</h2></div><span class="badge ${on?'ok':'watch'}">${on?'On':'Off: decisions are recorded, nothing is sent'}</span></div>
      <p class="muted">Checked every few minutes. An email goes out at once only for a decision you must take today: a stage far outside its normal range, a stage below it three working days in a row, an order that will miss even in the best case, or a customer whose orders all stopped. At most 3 a day, never the same item twice in 24 hours; the rest waits for the 07:00 briefing or the 14:00 digest.</p>
      ${a?`<p><strong>Right now:</strong> ${now.length?now.length+' would email at once: '+now.map(x=>esc(x.title)).join('; '):'nothing needs an immediate email'}. ${digest} for the digest, ${watch} watch items for the briefing.</p>`:''}
      <div class="actions">${action('test-alert','Send me a test alert now')}<a href="#/messages">Watches &amp; receipts →</a></div>
      <p class="muted">Turn alert emails on or off with the tick box under Manager delivery preferences.</p></section>`;
  }
  async function load() {
    const root=document.getElementById('email-settings-content');if(!root||loading)return;
    loading=true;
    try{model=await api('email/settings');model.alerts=await api('alerts/preview').catch(()=>null);if(root.isConnected)root.innerHTML=content();}
    catch(e){root.innerHTML='<p>Unable to load email settings.</p>'+action('reload','Try again');notice(e.message);}
    finally{loading=false;}
  }
  function notice(text){const p=document.getElementById('email-notice');if(p)p.textContent=text;else toast(text);}
  settingsPage = function(){queueMicrotask(load);return head('Workspace settings','Manage your mailbox, recipients and daily morning briefing.')+`<p id="email-notice" role="status"></p><div id="email-settings-content"><section class="card">Loading email settings…</section></div><section class="card" style="margin-top:24px"><h2>Workspace preferences</h2><form id="email-local-preferences"><label class="field">Default watch inactivity threshold<select name="idle">${[1,2,3,5,7].map(n=>`<option value="${n}" ${String(n)===String(state.settings.idle)?'selected':''}>${n} calendar days</option>`).join('')}</select></label><label class="field field-inline"><input name="voice" type="checkbox" ${state.settings.voice?'checked':''}>Prefer voice entry</label><p class="muted">These workspace preferences are saved in this browser. <a href="#/predictions">Imported model export (historical predictions)</a> · <a href="briefing.html">AI briefing page</a></p><div class="actions"><button type="submit">Save workspace preferences</button>${btn('disconnect-workspace','Disconnect workspace')}</div></form></section>`;};
  activityPage = function(){queueMicrotask(loadActivity);return head('Activity log','Email deliveries and reviewed workspace actions.',btn('export-audit','Export workspace audit'))+`<section class="card"><div class="section-heading"><div><div class="eyebrow">AUTOMATIC EMAIL</div><h2>Email deliveries</h2></div>${action('refresh-activity','Refresh')}</div><p id="email-notice" role="status"></p><div id="email-activity">Loading deliveries…</div></section><section class="card" style="margin-top:24px"><h2>Workspace actions</h2><label class="field">Filter action type<select id="audit-filter"><option value="">All actions</option>${[...new Set(state.audit.map(a=>a.type))].map(t=>`<option>${esc(t)}</option>`).join('')}</select></label><div id="audit-results">${auditRows(state.audit)}</div></section>`;};
  async function loadActivity(){
    const root=document.getElementById('email-activity');if(!root)return;
    try{const data=await api('email/activity');if(!root.isConnected)return;root.innerHTML=data.entries.map(r=>`<details class="email-log"><summary><span>${esc(r.day)} · ${r.kind==='chase_email'?'Order chase-up':r.kind==='customer_email'?'Customer email':'Morning briefing'}${r.clock_run_id?' · Demo':''}</span><span class="email-log-recipient">${esc(r.recipient)}</span><span class="badge">${esc(labels[r.status]||r.status)}</span></summary><div class="email-log-detail"><p><strong>Scheduled:</strong> ${esc(r.scheduled_at)}<br><strong>Updated:</strong> ${esc(r.updated_at)}<br><strong>Recipient:</strong> ${esc(r.recipient)}<br>${r.department?`<strong>Department:</strong> ${esc(r.department)}<br>`:''}${r.order_ids?.length?`<strong>Orders:</strong> ${esc(r.order_ids.join(', '))}<br>`:''}<strong>Subject:</strong> ${esc(r.subject||'Not generated yet')}</p>${r.status==='accepted'?'<p>Microsoft accepted the email. Inbox delivery is not confirmed.</p>':''}${r.diagnostic?.message?`<p>${esc(r.diagnostic.message)}</p>`:''}${r.body?`<pre>${esc(r.body)}</pre>`:''}<small>Delivery reference: ${esc(r.id)}</small></div></details>`).join('')||'<div class="empty">No morning briefing deliveries yet. Scheduled deliveries will appear here, one row per day.</div>';}catch(e){root.innerHTML='<p>Unable to load delivery activity.</p>';notice(e.message);}
  }
  document.addEventListener('submit',async e=>{
    const form=e.target;
    if(form.id==='business-clock-form'){
      e.preventDefault();const button=e.submitter;const mode=button?.value==='live'?'live':'demo';
      const value=form.elements.business_time.value;
      if(mode==='demo'&&!value){notice('Choose a business date and time.');return;}
      button.disabled=true;
      try{await api('email/clock','PUT',{mode,version:model.clock.version,target:mode==='demo'?value+':00+08:00':null});location.reload();}catch(err){notice(err.message);button.disabled=false;}return;
    }
    if(form.id==='email-local-preferences'){e.preventDefault();const f=new FormData(form);state.settings={...state.settings,idle:f.get('idle'),voice:f.has('voice')};save();audit('Settings','Updated workspace preferences');toast('Workspace preferences saved.');return;}
    if(form.id!=='email-preferences')return;e.preventDefault();
    const b=form.querySelector('button[type=submit]');b.disabled=true;
    const f=new FormData(form),payload={version:model.preferences.version,manager_email:f.get('manager_email'),manager_name:f.get('manager_name'),subject_prefix:f.get('subject_prefix'),briefing_enabled:f.has('briefing_enabled'),alert_emails_enabled:f.has('alert_emails_enabled'),departments:Object.fromEntries(['KNITTING','ASSEMBLY','WASHING','PACKING'].map(d=>[d,f.get('department_'+d)||''])),customers:[...form.querySelectorAll('.email-contact')].map(row=>Object.fromEntries([...row.querySelectorAll('input')].map(i=>[i.name,i.value])))};
    try{const result=await api('email/settings','PUT',payload);model.preferences=result.preferences;document.getElementById('email-settings-content').innerHTML=content();notice('Email settings saved.');}catch(e){notice(e.message);}finally{b.disabled=false;}
  });
  document.addEventListener('click',async e=>{
    const b=e.target.closest('[data-email]');if(!b)return;const name=b.dataset.email;
    if(name==='remove-contact'){b.closest('.email-contact').remove();document.getElementById('contacts-empty').hidden=!!document.querySelector('.email-contact');return;}
    if(name==='add-contact'){document.getElementById('email-contacts').insertAdjacentHTML('beforeend',contact());document.getElementById('contacts-empty').hidden=true;return;}
    b.disabled=true;
    try{if(name==='reload')await load();if(name==='refresh-activity')await loadActivity();if(name==='connect'){const r=await api('email/connect','POST');location.assign(r.authorization_url);}if(name==='test-alert'&&confirm('Send a test alert email to '+model.preferences.manager_email+' now? It goes only to you and does not count against the daily limit.')){const r=await api('alerts/test','POST',{});notice(r.status==='accepted'||r.status==='sent'?'Test alert sent to '+r.recipient+': '+r.subject:r.status==='not_configured'?'Connect Outlook first; this is what would be sent: '+r.subject:r.status==='nothing_to_send'?'No open alert right now, so there is nothing to test with.':'Test alert status: '+r.status);}if(name==='disconnect'&&confirm('Disconnect Outlook? Automatic emails will require reconnecting this mailbox.')){await api('email/disconnect','POST',{});await load();}}catch(e){notice(e.message);}finally{b.disabled=false;}
  });
  render();
})();
