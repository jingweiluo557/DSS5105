'use strict';
const el = id => document.getElementById(id);
const notice = text => { el('notice').textContent = text; };
let pending = null, busy = false;
const labels = {accepted:'Microsoft accepted the request. Check Outlook Sent Items.', rejected:'Microsoft rejected the request. Check mailbox permissions and status.', unknown:'Delivery status is unknown. Check Sent Items before trying again.', submitting:'Submission started. If it does not update, check Sent Items before trying again.'};
function describe(result) {
  const d=result.diagnostic;
  const base=labels[result.status]||result.status;
  if(!d) return base+(result.status==='rejected'?' (No diagnostic details were saved for this older record.)':'');
  if(result.status==='accepted') return base;
  return base+'\n'+[d.http_status?'HTTP '+d.http_status:'',d.code,d.message,d.retry_after?'Wait at least '+d.retry_after+' seconds before trying again':''].filter(Boolean).join(' · ');
}
async function api(path, method='GET', data, confirmed=false) {
  if (!el('admin').value) throw new Error('Enter the administrator token.');
  const response = await fetch('/api/outlook/' + path, {method, headers:{
    'Authorization':'Bearer ' + el('admin').value,
    'X-ThreadPilot-Token':el('access').value, 'Content-Type':'application/json',
    ...(confirmed ? {'X-Confirm-Write':'true'} : {})},
    ...(data ? {body:JSON.stringify(data)} : {})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || (typeof result.detail === 'string' ? result.detail : 'Request failed. Check your input and configuration.'));
  return result;
}
function action(id, run) { el(id).onclick = async () => { if (busy) return; busy=true; el(id).disabled=true; try {await run();} catch(e) {notice(e.message);} finally {busy=false;el(id).disabled=false;} }; }
action('status', async () => {const s=await api('status');notice(!s.configured ? 'Missing configuration: '+s.missing.join(', ') : s.connected ? 'Connected: '+s.account : 'Configured. Connect your Outlook account to continue.');});
action('connect', async () => {const s=await api('connect','POST');location.assign(s.authorization_url);});
action('disconnect', async () => {if(confirm('Remove the Outlook authorization saved by this service?')) {await api('disconnect','POST',{},true);notice('Mailbox disconnected.');}});
el('preview').onclick = () => {
  const payload={to:el('to').value.split(',').map(x=>x.trim()).filter(Boolean),subject:el('subject').value.trim(),body:el('body').value.trim()};
  if(!payload.to.length||!payload.subject||!payload.body){notice('Enter recipients, a subject and a message.');return;}
  // Keep the same ID for retries of identical reviewed content, including response loss.
  if(!pending||JSON.stringify(pending.payload)!==JSON.stringify(payload)) pending={id:crypto.randomUUID(),payload};
  el('review-content').textContent='Recipients: '+payload.to.join(', ')+'\nSubject: '+payload.subject+'\n\n'+payload.body;
  el('review').showModal();
};
el('cancel').onclick=()=>el('review').close();
action('send', async () => {const result=await api('send','POST',{id:pending.id,...pending.payload,confirmed:true},true);el('review').close();notice(describe(result));});
action('history', async () => {const result=await api('messages');el('history-output').textContent=result.messages.map(m=>new Date(m.created*1000).toLocaleString('en-GB')+' · '+describe(m)+'\n'+m.to.join(', ')+'\n'+m.subject).join('\n\n')||'No delivery activity yet.';});
const outcome=new URLSearchParams(location.search).get('authorization');
if(outcome) {notice(outcome==='connected'?'Outlook connected. Enter your administrator token again to check the connection or send email.':'Authorization was not completed. Check the configuration and reconnect. If the problem continues, consult the troubleshooting guide.');history.replaceState(null,'',location.pathname);}
