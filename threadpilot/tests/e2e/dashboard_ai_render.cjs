/* Rendering regression checks for the GM home screen with explicit fixtures; no model or browser calls.
   Run from the project root: node tests/e2e/dashboard_ai_render.cjs */
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const context = vm.createContext({
  window: {addEventListener() {}}, document: {addEventListener() {}},
  route: 'test', render() {}, esc: String, openAIDrawer() {}, closeOverlay: {}, toast() {}, go() {}, scrollY: 0,
  btn: (action, label, cls = '', extra = '') => `<button data-action="${action}" ${extra}>${label}</button>`,
  link: (r, label, id = '', cls = '') => `<a class="${cls}" href="#/${r}${id ? '?id=' + id : ''}">${label}</a>`,
  find: id => (['ORD-029', 'ORD-108', 'ORD-120'].includes(id) ? {id} : null),
  composer: () => '<form class="composer" data-form="chat"><textarea name="visible-question"></textarea></form>',
  formatWorkspaceTime: v => String(v).slice(0, 16).replace('T', ' '),
  titleCase: s => s.toLowerCase().replace(/\b\w/g, c => c.toUpperCase()),
  date: d => d, TODAY: '2026-04-01',
  orders: [], activeOrders: [], overdue: [], dueToday: [], idleOrders: [], stageStats: [],
});
vm.runInContext(fs.readFileSync('frontend/dashboard.js', 'utf8'), context);
vm.runInContext(`homeData={business_date:'2026-04-01',status:{colour:'red',label:'RED',date_label:'Wed 1 Apr',facts:['8 overdue','Assembly -39% for 6 days','3 decisions need you'],meaning:'A decision today changes the outcome.'},
 decisions:[{key:'stage_drop:ASSEMBLY',tier:'P1',kind:'stage_drop',entity:'ASSEMBLY',title:'Assembly 39% below range',lines:['6 working days below its normal range, since 25 Mar'],action:{label:'Ask the floor',kind:'chat',message:'Draft a chase-up to the assembly department.'}},
  {key:'will_miss:ORD-029',tier:'P1',kind:'will_miss',entity:'ORD-029',title:'ORD-029 will miss 1 Apr',lines:['Northwind Apparel, 1,500 Beanie, at washing','best case 13 Apr'],action:{label:'Review options',kind:'route',value:'risk?id=ORD-029'},options:['expedite','outsource','new date']}],
 more_waiting:29,counts:{in_progress:34,overdue:8,due_today:1,idle:2,total:120},
 health:{late:8,at_risk:26,on_track:0,unknown:0,active:34,on_time_rate:57,on_time_basis:'20 of 35',on_time_change_pts:-4},
 pulse:[{stage:'KNITTING',date:'2026-03-31',pieces:905,band:{min:797,max:1018,mean:913.9,samples:8},status:'within',change_pct:-1,below_days:0},
        {stage:'ASSEMBLY',date:'2026-03-31',pieces:455,band:{min:687,max:807,mean:745.2,samples:8},status:'below',change_pct:-39,below_days:6},
        {stage:'WASHING',date:'2026-03-31',pieces:732,band:{min:617,max:774,mean:708.8,samples:8},status:'within',change_pct:3,below_days:0},
        {stage:'PACKING',date:'2026-03-31',pieces:657,band:{min:562,max:734,mean:667.8,samples:8},status:'within',change_pct:-2,below_days:0}]};
dashboardData={ai_briefing:{generated_at:'2026-04-01T07:02:00+08:00',yesterday:'- Assembly 455 vs 700.3 baseline. Second sentence stays in the full briefing.',top_issue:'- Nine orders are overdue.\\n- Second issue',decide:'- Re-date ORD-120 with TrendCart.\\n- Ask the floor at assembly.'},
 tasks:[{id:'manual:1',title:'Call planner',origin:'manual',done:false,version:1,reasons:[]},
        {id:'ai:1',title:'Verify the current status of overdue orders',origin:'ai',done:false,version:1,reasons:['AI recommendation']},
        {id:'ai:2',title:'Re-date ORD-120 with TrendCart',order_id:'ORD-120',origin:'ai',done:false,version:1,reasons:['AI recommendation']},
        {id:'auto:1',title:'ORD-107 · Northwind',origin:'auto',done:false,version:1,reasons:['Overdue']},
        {id:'ai:3',title:'Completed action',origin:'ai',done:true,version:2,reasons:[]}]};`, context);

let html = vm.runInContext('statusLine()', context);
assert(html.includes('status-line red') && html.includes('Wed 1 Apr · RED') && html.includes('3 decisions need you'));

html = vm.runInContext('kpiStrip()', context);
assert(html.includes('<strong>8</strong> overdue') && html.includes('<strong>26</strong> at risk') && html.includes('57%'));

html = vm.runInContext('decisionCards()', context);
assert(html.includes('DECIDE TODAY') && html.includes('29 more in Risk orders'));
assert(html.includes('data-action="decide-chat"') && html.includes('data-message="Draft a chase-up to the assembly department."'));
assert(html.includes('data-action="decide-route"') && html.includes('data-route="risk?id=ORD-029"'));
assert((html.match(/<article class="decision/g) || []).length === 2, 'one card per decision');

html = vm.runInContext('healthCard()', context);
assert(html.includes('8 late') && html.includes('26 at risk') && html.includes('0 on track') && html.includes('On time 57%') && html.includes('-4 pts'));

html = vm.runInContext('pulseCard()', context);
assert(html.includes('pbar below') && html.includes('-39% · 6 d') && (html.match(/pulse-col/g) || []).length === 4);
assert(html.includes('Assembly is 39% under its normal range and has been for 6 working days'));

html = vm.runInContext('briefingCard()', context);
assert(html.includes('written 2026-04-01 07:02') && html.includes('Assembly 455 vs 700.3 baseline.') && !html.includes('Second sentence'), 'first sentence only');
assert(html.includes('Nine orders are overdue.') && !html.includes('Second issue') && html.includes('Open the full briefing'));

html = vm.runInContext('todosCard()', context);
assert(html.includes('Call planner') && html.includes('Re-date ORD-120'), 'manual and order-named AI tasks stay');
assert(!html.includes('Verify the current status'), 'verify sentences are dropped');
assert(!html.includes('ORD-107 · Northwind'), 'auto risk rows are not to-dos');
assert(html.includes('2 open · 1 handled'));

vm.runInContext("homeData=null;overdue=[{id:'ORD-107',customer:'Northwind',qty:2000,product:'Cardigan',stage:'PACKING',due:'2026-03-16',daysToDue:-16}];activeOrders=overdue;stageStats=[{stage:'ASSEMBLY',latest:{date:'2026-03-31',pieces_completed:455},change:-35}]", context);
html = vm.runInContext('dashboard()', context);
assert(html.includes('status-line amber') && html.includes('ORD-107 is 16 days late') && html.includes('Confirm a new date'), 'fallback without /api/dashboard/home');
console.log('Dashboard home rendering checks passed.');
