const vm=require('vm'),fs=require('fs'),assert=require('assert/strict');
const code=fs.readFileSync('frontend/config.js','utf8');
function resolve(page,apiBase){const u=new URL(page),ctx={URL,location:u,window:{THREADPILOT_CONFIG:{apiBase}}};vm.runInNewContext(code,ctx);return ctx.window}
for(const origin of ['http://127.0.0.1:8000','http://localhost:8765','http://192.168.1.20:8765','http://192.168.1.20:8000','https://factory.example'])assert.equal(resolve(origin).THREADPILOT_API_BASE,origin);
assert.equal(resolve('https://factory.example','https://api.factory.example/').THREADPILOT_API_BASE,'https://api.factory.example');
for(const base of ['http://127.0.0.1:8000','http://localhost:8000','http://[::1]:8000'])assert(resolve('http://192.168.1.20:8765',base).THREADPILOT_CONFIG_ERROR);
for(const base of ['http://api.factory.example','https://user:pw@api.factory.example','https://api.factory.example/chat'])assert(resolve('https://factory.example',base).THREADPILOT_CONFIG_ERROR);
console.log('PASS: same-origin on desktop/LAN/mobile/static port; explicit HTTPS backend; reject remote loopback, mixed-content and malformed origins.');
