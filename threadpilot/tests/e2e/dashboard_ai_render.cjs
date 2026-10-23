/* Rendering regression checks with explicit fixtures; no model or browser calls. */
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const context = vm.createContext({
  window: {addEventListener() {}}, document: {addEventListener() {}},
  route: 'test', render() {}, esc: String, openAIDrawer() {},
  btn: (action, label) => `<button data-action="${action}">${label}</button>`,
  link: (_, label) => `<a>${label}</a>`, find: () => null,
});
vm.runInContext(fs.readFileSync('frontend/dashboard.js', 'utf8'), context);
vm.runInContext(`dashboardData={briefing_preview:{yesterday:'RULE SUMMARY'},tasks:[
 {id:'ai:1',title:'Check production progress',origin:'ai',done:false,reasons:['AI recommendation']},
 {id:'auto:1',title:'RISK ORDER',origin:'auto',done:false,reasons:['Overdue']},
 {id:'manual:1',title:'Call planner',origin:'manual',done:false,reasons:[]},
 {id:'ai:2',title:'Completed action',origin:'ai',done:true,reasons:[]}
]};`, context);
let html = vm.runInContext('morningSummary()', context);
assert(!html.includes('RULE SUMMARY') && !html.includes('Full briefing'));
html = vm.runInContext('todoPanel()', context);
assert(html.includes('Check production progress') && html.includes('Call planner'));
assert(!html.includes('<strong>RISK ORDER</strong>'));
assert(html.includes('Risk orders') && html.includes('dash-task-chase'));
html = vm.runInContext("taskView='risk';todoPanel()", context);
assert(html.includes('<strong>RISK ORDER</strong>'));
assert(!html.includes('<strong>Check production progress</strong>'));
html = vm.runInContext("taskView='done';todoPanel()", context);
assert(html.includes('Completed action'));
vm.runInContext("morningReport={yesterday:'Production review',top_issue:'- First issue\\n- Second issue',decide:'- Check progress'}", context);
html = vm.runInContext('morningSummary()', context);
assert(html.includes('<li>First issue</li>') && html.includes('Draft chase-up'));
html = vm.runInContext('morningLoading=true;morningSummary()', context);
assert(html.includes('Analyzing') && !html.includes('Production review'));
console.log('Dashboard AI rendering checks passed.');
