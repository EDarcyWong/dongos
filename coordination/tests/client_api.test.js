const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../dongos_coordination/web/app.js'),'utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('\nasync function action'));
function fixture(responses){const calls=[];const context=vm.createContext({fetch:async(url,options={})=>{calls.push({url,options:JSON.parse(JSON.stringify(options))});assert.ok(responses.length,'unexpected extra retry');const [status,value]=responses.shift();return {status,ok:status>=200&&status<300,json:async()=>value};}});vm.runInContext('let projectId="alpha",csrf="old";'+api+';globalThis.request=api;',context);return {context,calls};}
test('stale mutation nonce refreshes session and retries exactly once',async()=>{const {context,calls}=fixture([[403,{error:'token'}],[200,{csrf:'fresh'}],[200,{ok:true}]]);assert.equal((await context.request('/api/doctor',{})).ok,true);assert.deepEqual(calls.map(x=>x.url),['/api/doctor','/api/session','/api/doctor']);assert.equal(calls[0].options.headers['X-Coordinator-CSRF'],'old');assert.equal(calls[2].options.headers['X-Coordinator-CSRF'],'fresh');assert.equal(calls[2].options.headers['X-Coordination-Project'],'alpha');});
test('persistent 403 is reported without a retry loop',async()=>{const {context,calls}=fixture([[403,{}],[200,{csrf:'fresh'}],[403,{error:'origin refused'}]]);await assert.rejects(context.request('/api/action',{}),/origin refused/);assert.equal(calls.length,3);});
test('GET and CAS conflict never replay a mutation',async()=>{let f=fixture([[403,{error:'host refused'}]]);await assert.rejects(f.context.request('/api/snapshot'),/host refused/);assert.equal(f.calls.length,1);f=fixture([[409,{error:'stale revision'}]]);await assert.rejects(f.context.request('/api/action',{}),/stale revision/);assert.equal(f.calls.length,1);});
