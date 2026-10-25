/* Live database snapshot. No bundled data fallback. */
const frontendAssetQuery = new URL(document.currentScript.src).search;
(async function loadDatabaseSnapshot() {
  const app = document.getElementById('app');
  app.textContent = 'Loading current factory records…';
  try {
    if(window.THREADPILOT_CONFIG_ERROR)throw new Error(window.THREADPILOT_CONFIG_ERROR);
    const response = await window.threadpilotFetch(window.THREADPILOT_API_BASE + '/api/snapshot', {cache: 'no-store'});
    if (response.status === 401) throw new Error('Enter the workspace access key to load the current records.');
    if (!response.ok) throw new Error('Database unavailable. Check migrations and connection settings.');
    const data = await response.json();
    if (!data.orders?.length || !data.production_log?.length || !data.workshops?.length)
      throw new Error('Import orders, production_log and workshops before opening the dashboard.');
    if (!['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'].every(stage => data.production_log.some(row => row.stage === stage && new Date(row.date + 'T12:00:00Z').getUTCDay() !== 0)))
      throw new Error('Dashboard needs a working-day production record for each stage. Data APIs remain available.');
    window.TRACK1_DATA = data;
    const clockResponse = await window.threadpilotFetch(window.THREADPILOT_API_BASE + '/api/email/clock', {cache:'no-store'});
    if(!clockResponse.ok)throw new Error('Business clock unavailable.');
    window.threadpilotClock = await clockResponse.json();
    window.threadpilotClockAnchor = performance.now();
    window.threadpilotNow = () => new Date(Date.parse(window.threadpilotClock.now) + (window.threadpilotClock.mode==='legacy'?0:performance.now()-window.threadpilotClockAnchor));
    const riskResponse = await window.threadpilotFetch(window.THREADPILOT_API_BASE + '/api/scheduling/risk', {cache:'no-store'});
    if (!riskResponse.ok) throw new Error('Queue risk unavailable. Run database migrations and retry.');
    window.QUEUE_DATA = await riskResponse.json();
    app.style.visibility = 'hidden';
    for (const file of ['app.js', 'data-views.js', 'ai-api.js', 'ai-stream.js', 'workspace.js', 'dashboard.js', 'predictions.js', 'review-drafts.js', 'scheduling.js', 'email-settings.js', 'email-chase.js', 'feasibility-chart.js', 'voice.js']) {
      await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = file + frontendAssetQuery; script.onload = resolve; script.onerror = reject;
        document.body.appendChild(script);
      });
    }
    app.style.visibility = '';
    setInterval(()=>{
      const stamp = document.querySelector('.freshness');
      if(stamp) stamp.textContent='Business time · '+new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(window.threadpilotNow());
    },1000);
    let clockChecking=false;
    setInterval(async()=>{
      if(clockChecking)return;clockChecking=true;
      try{
        const r=await window.threadpilotFetch(window.THREADPILOT_API_BASE+'/api/email/clock',{cache:'no-store'});
        if(!r.ok)return;
        const next=await r.json();
        const day=new Date(Date.parse(next.now)+8*3600000).toISOString().slice(0,10);
        if(next.version!==window.threadpilotClock.version||day!==window.TRACK1_DATA.today){location.reload();return;}
        window.threadpilotClock=next;window.threadpilotClockAnchor=performance.now();
      }catch{}finally{clockChecking=false;}
    },10000);
  } catch (error) {
    app.style.visibility = '';
    app.textContent = 'Unable to load current data: ' + (error.message || 'network error');
  }
})();
