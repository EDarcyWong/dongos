// Dependency-free DOM contract tests. These do not render CSS or replace browser QA.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../dongos_coordination/web/index.html'),'utf8');
const source=fs.readFileSync(path.join(__dirname,'../dongos_coordination/web/app.js'),'utf8');
function documentFixture(){
  let doc;
  class Element {
    constructor(tag,attrs={}){this.tagName=tag;this.attrs=attrs;this.children=[];this.parent=null;this.dataset={};this.events={};this.style={};this._text='';this.id=attrs.id||'';this.className=attrs.class||'';this.value=attrs.value||'';this.type=attrs.type||'';this.disabled='disabled' in attrs;this.checked='checked' in attrs;this.hidden='hidden' in attrs;this.open=false;this.scrollTop=0;this.isConnected=true;for(const [key,value]of Object.entries(attrs))if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;}
    get classList(){return {add:(c)=>{this.className+=' '+c;},remove:(c)=>{this.className=this.className.split(/\s+/).filter(x=>x!==c).join(' ');},contains:(c)=>this.className.split(/\s+/).includes(c),toggle:(c,on)=>{const classes=new Set(this.className.split(/\s+/));if(on??!classes.has(c))classes.add(c);else classes.delete(c);this.className=[...classes].join(' ');}};}
    append(...items){for(let item of items){if(typeof item==='string'){const t=new Element('#text');t.textContent=item;item=t;}item.parent=this;this.children.push(item);}}
    replaceChildren(...items){for(const child of this.children){child.parent=null;child.isConnected=false;}this.children=[];this._text='';this.append(...items);}
    replaceWith(item){const at=this.parent.children.indexOf(this);item.parent=this.parent;this.parent.children[at]=item;this.isConnected=false;}
    set textContent(value){this.replaceChildren();this._text=String(value??'');}get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
    setAttribute(key,value){if(key==='id')this.id=value;else if(key==='class')this.className=value;else if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(value);else this.attrs[key]=String(value);}
    getAttribute(key){if(key==='id')return this.id;if(key==='class')return this.className;if(key==='type')return this.type;if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())];return this.attrs[key];}
    matches(selector){if(selector.startsWith('.'))return this.className.split(/\s+/).includes(selector.slice(1));if(selector.startsWith('#'))return this.id===selector.slice(1);const m=selector.match(/^([a-z][a-z0-9-]*)?(?:\[([^=\]]+)(?:=['"]?([^'"\]]+)['"]?)?\])?$/);return !!m&&(!m[1]||this.tagName===m[1])&&(!m[2]||(m[3]===undefined?this.getAttribute(m[2])!==undefined:this.getAttribute(m[2])===m[3]));}
    querySelectorAll(selector){return this.children.flatMap(c=>[...(c.matches(selector)?[c]:[]),...c.querySelectorAll(selector)]);}querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
    addEventListener(name,fn){(this.events[name]??=[]).push(fn);}async emit(name,extra={}){if(name==='click'&&this.disabled)return;for(const fn of this.events[name]||[])await fn({target:this,currentTarget:this,preventDefault(){},...extra});}
    focus(){doc.activeElement=this;}showModal(){this.open=true;}show(){this.open=true;}close(){this.open=false;this.emit('close');}click(){return this.emit('click');}
    get elements(){return Object.fromEntries(this.querySelectorAll('[name]').map(e=>[e.attrs.name,e]));}
    reset(){for(const e of Object.values(this.elements)){e.value=e.tagName==='select'?e.querySelector('option')?.value||'':e.attrs.value||'';e.checked=false;}}
  }
  const root=new Element('root'),stack=[root],voids=new Set(['meta','link','input','br','hr','img']);
  for(const token of html.matchAll(/<![^>]*>|<\/?[A-Za-z][^>]*>|[^<]+/g)){
    const t=token[0];if(t.startsWith('<!'))continue;
    if(t.startsWith('</')){stack.pop();continue;}
    if(t.startsWith('<')){const tag=t.match(/^<([\w-]+)/)[1],attrs={};const tail=t.slice(tag.length+1,-1);for(const a of tail.matchAll(/([\w-]+)(?:="([^"]*)")?/g))attrs[a[1]]=a[2]??'';const e=new Element(tag,attrs);stack.at(-1).append(e);if(!voids.has(tag))stack.push(e);}
    else {const e=new Element('#text');e._text=t;stack.at(-1).append(e);}
  }
  doc={body:root.querySelector('body'),documentElement:root.querySelector('html'),activeElement:null,events:{},addEventListener(name,fn){(this.events[name]??=[]).push(fn);},async emit(name,extra={}){for(const fn of this.events[name]||[])await fn({preventDefault(){},...extra});},createElement:t=>new Element(t),createTextNode:text=>{const t=new Element('#text');t._text=text;return t;},getElementById:id=>root.querySelector('#'+id),querySelector:s=>root.querySelector(s),querySelectorAll:s=>root.querySelectorAll(s)};
  for(const e of root.querySelectorAll('select'))e.value=e.querySelector('option')?.value||'';
  return doc;
}
function task(i,status='todo',owner=null){return {id:(owner||'pool')+':T'+i,number:'T'+i,title:'任务 '+i,description:'完整任务说明\n第二段',owner,status,rev:1,write_paths:['pool-works/docs/'+i+'.md'],checks:[],depends_on:[],updated_at:'2026-10-19T00:00:00Z',claimed_by:null,auto_dispatch:false,auto_verify:false,timing:{published_at:null,rounds:[],latest_round:null,verifications:[],timeline:[],history_incomplete:true}};}
function app(tasks){
  const document=documentFixture(),requests=[];
  const snapshot={tasks,jobs:[],events:[],issues:[],providers:{},automation:false,labels:{todo:'待领取',in_progress:'进行中',submitted:'待复验',rework:'返修',paused:'暂停'}};
  let respond=async(url,data)=>url==='/api/snapshot'?snapshot:{};
  const location={hash:''},window={events:{},addEventListener(name,fn){(this.events[name]??=[]).push(fn);}};
  const context=vm.createContext({document,window,location,navigator:{clipboard:{writeText:async()=>{}}},console,Date,Map,Set,URL,Blob,setTimeout,setInterval(){},localStorage:{getItem(){return null;},setItem(){}},fetch:async(url,options={})=>{const data=options.body?JSON.parse(options.body):undefined;requests.push({url,data});const result=await respond(url,data);return {status:200,ok:true,json:async()=>result};},snapshot});
  vm.runInContext(source.replace('}boot();','}')+"\nprojectId='demo'; state=snapshot; globalThis.app={render,showTask,showCreate,renderTaskMetrics,taskElapsed,go,attentionGroups};",context);
  return {document,location,window,requests,snapshot,api:context.app,setRespond:fn=>respond=fn,run:code=>vm.runInContext(code,context)};
}

test('theme toggle switches the workbench to dark and back',async()=>{
  const f=app([]),html=f.document.documentElement,toggle=f.document.getElementById('theme-toggle');
  assert.equal(html.getAttribute('data-theme'),'light');
  assert.equal(toggle.getAttribute('aria-pressed'),'false');
  await toggle.click();
  assert.equal(html.getAttribute('data-theme'),'dark');
  assert.equal(toggle.getAttribute('aria-pressed'),'true');
  assert.equal(toggle.querySelector('.theme-icon').textContent,'☀');
  await toggle.click();
  assert.equal(html.getAttribute('data-theme'),'light');
});

test('accepted roadmap nodes separate future scope from actual stage work',()=>{
  const f=app([]);
  const roadmap=JSON.parse(fs.readFileSync(path.join(__dirname,'../dongos_works/roadmap.json'),'utf8'));
  f.snapshot.roadmap=roadmap;
  for(const [track,id] of [['coordination','P5CTX2'],['coordination','P5CTX1'],['coordination','P2LIVE1'],['language','L3B'],['integration','M7'],['integration','M10']]){
    f.run(`selectRoadmapStage(${JSON.stringify(track+':'+id)})`);
    const detail=f.document.getElementById('roadmap-detail');
    assert.ok(detail.textContent.includes('已通过验收'));
    assert.ok(detail.textContent.includes('本项既定范围内无待办'));
    assert.ok(detail.textContent.includes('验收范围与后续归属'));
    assert.ok(!detail.querySelectorAll('h4').some(h=>h.textContent==='尚待完成'),id);
    const stage=roadmap.tracks.find(t=>t.id===track).stages.find(s=>s.id===id);
    assert.equal(stage.remaining.length,0,id);
    for(const note of stage.scope_notes)assert.ok(detail.querySelector('.roadmap-detail-scope').textContent.includes(note));
  }
  for(const id of ['P2','P5']){
    f.run(`selectRoadmapStage(${JSON.stringify('system:'+id)})`);
    const detail=f.document.getElementById('roadmap-detail');
    assert.ok(detail.textContent.includes('部分完成'));
    assert.ok(detail.querySelectorAll('h4').some(h=>h.textContent==='尚待完成'));
    const stage=roadmap.tracks.find(t=>t.id==='system').stages.find(s=>s.id===id);
    for(const item of stage.remaining)assert.ok(detail.querySelector('.roadmap-detail-columns').textContent.includes(item));
  }
});

test('full app boots DOM bindings, renders list pages and applies status/member/search shortcuts',async()=>{
  const f=app(Array.from({length:25},(_,i)=>task(i,i<3?'in_progress':'todo',i<3?'cursor':null)));
  f.api.render();assert.equal(f.document.getElementById('task-rows').children.length,20);
  await f.document.getElementById('page-next').click();assert.equal(f.document.getElementById('task-rows').children.length,5);
  const quick=f.document.querySelectorAll('[data-quick]').find(e=>e.dataset.quick==='in_progress');await quick.click();assert.equal(f.document.getElementById('task-rows').children.length,3);
  const owner=f.document.getElementById('owner-filter');owner.value='unassigned';await owner.emit('change');assert.equal(f.document.getElementById('task-rows').children.length,0);assert.equal(f.document.getElementById('empty').hidden,false);
  await f.document.getElementById('progress-reset').click();const search=f.document.getElementById('search');search.value='任务 24';await search.emit('input');assert.equal(f.document.getElementById('task-rows').children.length,1);
  await f.document.getElementById('view-board').click();assert.equal(f.document.body.dataset.view,'board');assert.equal(f.document.getElementById('view-board').getAttribute('aria-pressed'),'true');
});

test('new task defaults to public ownership with scoped paths and no automatic execution',()=>{
  const f=app([task(1)]);f.api.showCreate();const form=f.document.getElementById('create-form');
  assert.equal(form.elements.owner.value,'');assert.equal(form.elements.dispatch.disabled,true);assert.equal(form.elements.id.value,'T2');assert.equal(form.elements.write_paths.value,'pool-works/src/t2.dg');assert.equal(f.document.getElementById('create-dialog').open,true);
});

test('task details preserve text, show actual elapsed values and never invent missing history',async()=>{
  const item=task(1,'in_progress','cursor');item.claimed_by='cursor-a';item.claimed_at='2026-10-19T00:00:00Z';item.timing.latest_round={owner:'cursor',claimed_at:item.claimed_at,elapsed_seconds:65,ongoing:true};
  const f=app([item]);await f.api.showTask(item.id);const body=f.document.getElementById('detail-body');
  assert.ok(body.textContent.includes('1分5秒'));assert.ok(body.textContent.includes('完整任务说明\n第二段'));assert.ok(body.textContent.includes('执行完成（提交）'));assert.ok(body.textContent.includes('等待提交'));
  assert.equal(f.api.taskElapsed(task(2)),'—');
});

test('external stop confirmation is a separate explicit checkbox plus evidence, never implied by pause',async()=>{
  const item=task(1,'in_progress','cursor');Object.assign(item,{claimed_by:'cursor-a',pause_requested_at:'2026-10-19T00:00:00Z',pause_control:'external'});
  const f=app([item]);f.setRespond(async url=>url==='/api/snapshot'?f.snapshot:item);await f.api.showTask(item.id);
  const body=f.document.getElementById('detail-body'),panel=body.querySelector('.handoff-panel');
  assert.equal(body.querySelector('.transfer-section'),null);
  const confirm=panel.querySelector('button');assert.equal(confirm.disabled,true);await confirm.click();assert.equal(f.requests.length,0);
  const checkbox=panel.querySelector('input');checkbox.checked=true;await checkbox.emit('change');assert.equal(confirm.disabled,true);
  const evidence=panel.querySelector('.handoff-note');evidence.value='原客户端执行已终止';await evidence.emit('input');assert.equal(confirm.disabled,false);
  await confirm.click();const writes=f.requests.filter(r=>r.url==='/api/action');assert.equal(writes.length,1);assert.equal(writes[0].data.action,'confirm_pause');assert.equal(writes[0].data.options.stopped_confirmed,true);assert.equal(writes[0].data.note,'原客户端执行已终止');
});

test('double clicks send one mutation and a dismissed task dialog is not reopened by its response',async()=>{
  const item=task(1);const f=app([item]);let release;f.setRespond(async(url)=>url==='/api/action'?new Promise(resolve=>release=resolve):f.snapshot);
  await f.api.showTask(item.id);const button=f.document.getElementById('detail-body').querySelectorAll('button').find(b=>b.textContent==='领取公共任务');
  const pending=button.click();await button.click();assert.equal(f.requests.filter(r=>r.url==='/api/action').length,1);
  f.document.getElementById('detail-dialog').close();release(item);await pending;assert.equal(f.document.getElementById('detail-dialog').open,false);
});

test('pages route through the hash, and members and stat tiles jump to filtered task lists',async()=>{
  const items=[task(1,'in_progress','cursor'),task(2,'submitted','claude'),task(3,'accepted','claude'),task(4)];
  const f=app(items);f.api.render();
  assert.equal(f.document.body.dataset.page,'overview');
  f.api.go('runtime');assert.equal(f.document.body.dataset.page,'runtime');assert.equal(f.location.hash,'runtime');assert.equal(f.document.getElementById('page-title').textContent,'执行与环境');
  f.location.hash='nonsense';for(const fn of f.window.events.hashchange)fn();assert.equal(f.document.body.dataset.page,'overview');
  const claude=f.document.querySelectorAll('[data-owner]').find(b=>b.dataset.owner==='claude');
  assert.equal(f.document.querySelectorAll('[data-owner-count]').find(e=>e.dataset.ownerCount==='claude').textContent,'1');
  await claude.click();assert.equal(f.document.body.dataset.page,'tasks');assert.equal(f.document.getElementById('task-rows').children.length,2);
  const stat=f.document.querySelectorAll('[data-jump]').find(b=>b.dataset.jump==='submitted');await stat.click();
  assert.equal(f.document.getElementById('owner-filter').value,'');assert.equal(f.document.getElementById('task-rows').children.length,1);
  assert.equal(f.document.querySelectorAll('[data-count]').find(e=>e.dataset.count==='active').textContent,'3');
  assert.equal(f.document.getElementById('nav-count-tasks').textContent,'3');
});

test('overview attention groups follow real states and dependencies without counting submissions as done',()=>{
  const blocked=task(5);blocked.depends_on=['pool:T2'];
  const stopping=task(6,'in_progress','cursor');stopping.pause_requested_at='2026-10-19T00:00:00Z';stopping.pause_control='external';
  const items=[task(1),task(2,'submitted','claude'),task(3,'rework','cursor'),task(4,'accepted','claude'),blocked,stopping];
  items[1].verification={passed:true,summary:'ok'};
  const f=app(items);f.api.render();
  const groups=Object.fromEntries(f.api.attentionGroups().map(g=>[g.key,g.items.map(t=>t.id)]));
  assert.deepEqual(groups.ready,['pool:T1']);assert.deepEqual(groups.blocked,['pool:T5']);assert.deepEqual(groups.submitted,['claude:T2']);
  assert.deepEqual(groups.stopping,['cursor:T6']);assert.equal(groups.in_progress,undefined);assert.deepEqual(groups.integrate,['claude:T4']);
  assert.equal(f.document.getElementById('accepted').textContent,'1');assert.equal(f.document.getElementById('nav-count-overview').textContent,'3');
  assert.ok(f.document.getElementById('attention-list').textContent.includes('复验通过 · 待验收'));
});

test('task drawer is non-modal, steps through the visible list and closes on Escape',async()=>{
  const f=app([task(1),task(2),task(3,'accepted','claude')]);f.api.go('tasks');f.api.render();
  const quick=f.document.querySelectorAll('[data-quick]').find(e=>e.dataset.quick==='active');await quick.click();
  await f.api.showTask('pool:T1');const drawer=f.document.getElementById('detail-dialog');
  assert.equal(drawer.open,true);assert.equal(f.document.body.dataset.drawer,'open');assert.equal(f.document.getElementById('detail-prev').disabled,true);
  await f.document.getElementById('detail-next').click();assert.equal(f.document.getElementById('detail-title').textContent,'任务 2');
  assert.equal(f.document.getElementById('detail-next').disabled,true);
  await f.document.emit('keydown',{key:'Escape',target:f.document.body});assert.equal(drawer.open,false);assert.equal(f.document.body.dataset.drawer,'');
  await f.document.emit('keydown',{key:'/',target:f.document.body});assert.equal(f.document.activeElement?.id,'search');
});
