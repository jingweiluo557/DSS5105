'use strict';
const el = id => document.getElementById(id);
const notice = text => { el('notice').textContent = text; };
let pending = null, busy = false;
const labels = {accepted:'Microsoft 已接受发送请求，请到 Outlook 已发送中核对', rejected:'Microsoft 拒绝了发送请求，请检查权限和邮箱状态', unknown:'提交结果不明，请先检查已发送，避免重复发送', submitting:'提交已开始；若长时间未更新，请检查已发送，勿重复发送'};
function describe(result) {
  const d=result.diagnostic;
  const base=labels[result.status]||result.status;
  if(!d) return base+(result.status==='rejected'?'（旧记录未保存具体错误原因）':'');
  if(result.status==='accepted') return base;
  return base+'\n'+[d.http_status?'HTTP '+d.http_status:'',d.code,d.message,d.retry_after?'请至少等待 '+d.retry_after+' 秒后再尝试':''].filter(Boolean).join(' · ');
}
async function api(path, method='GET', data, confirmed=false) {
  if (!el('admin').value) throw new Error('请输入 DATA_API_TOKEN 管理令牌。');
  const response = await fetch('/api/outlook/' + path, {method, headers:{
    'Authorization':'Bearer ' + el('admin').value,
    'X-ThreadPilot-Token':el('access').value, 'Content-Type':'application/json',
    ...(confirmed ? {'X-Confirm-Write':'true'} : {})},
    ...(data ? {body:JSON.stringify(data)} : {})});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || (typeof result.detail === 'string' ? result.detail : '请求失败，请核对输入和配置。'));
  return result;
}
function action(id, run) { el(id).onclick = async () => { if (busy) return; busy=true; el(id).disabled=true; try {await run();} catch(e) {notice(e.message);} finally {busy=false;el(id).disabled=false;} }; }
action('status', async () => {const s=await api('status');notice(!s.configured ? '缺少配置：'+s.missing.join(', ') : s.connected ? '已连接：'+s.account : '配置已就绪，尚未连接 Outlook。');});
action('connect', async () => {const s=await api('connect','POST');location.assign(s.authorization_url);});
action('disconnect', async () => {if(confirm('删除此服务保存的 Outlook 授权缓存？')) {await api('disconnect','POST',{},true);notice('已断开本机连接。');}});
el('preview').onclick = () => {
  const payload={to:el('to').value.split(',').map(x=>x.trim()).filter(Boolean),subject:el('subject').value.trim(),body:el('body').value.trim()};
  if(!payload.to.length||!payload.subject||!payload.body){notice('请填写收件人、主题和正文。');return;}
  // Keep the same ID for retries of identical reviewed content, including response loss.
  if(!pending||JSON.stringify(pending.payload)!==JSON.stringify(payload)) pending={id:crypto.randomUUID(),payload};
  el('review-content').textContent='收件人：'+payload.to.join(', ')+'\n主题：'+payload.subject+'\n\n'+payload.body;
  el('review').showModal();
};
el('cancel').onclick=()=>el('review').close();
action('send', async () => {const result=await api('send','POST',{id:pending.id,...pending.payload,confirmed:true},true);el('review').close();notice(describe(result));});
action('history', async () => {const result=await api('messages');el('history-output').textContent=result.messages.map(m=>new Date(m.created*1000).toLocaleString()+' · '+describe(m)+'\n'+m.to.join(', ')+'\n'+m.subject).join('\n\n')||'暂无记录。';});
const outcome=new URLSearchParams(location.search).get('authorization');
if(outcome) {notice(outcome==='connected'?'Outlook 授权成功。重新输入管理令牌后可检查连接和发送邮件。':'授权未完成。请检查配置后重新连接；若已点击接受仍失败，请查看排错文档。');history.replaceState(null,'',location.pathname);}
