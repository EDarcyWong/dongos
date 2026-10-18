'use strict';
const $ = id => document.getElementById(id);
const names = {codex:'Codex',cursor:'Cursor',claude:'Claude',deepseek:'DeepSeek',lmstudio:'LM Studio',python:'Python'};
const eventNames = {imported:'导入历史任务',created:'发布任务',claim:'领取任务',started:'CLI开始执行',submit:'提交交付',queued:'加入执行队列',verified:'完成定向复验',accept:'独立验收通过',integrate:'确认集成',rework:'要求返修',document_changed:'任务书更新',job_finished:'作业结束',pause:'暂停任务',resume:'恢复任务',automation:'更新自动化设置',implementation_finished:'收集实现结果',cancel_requested:'请求取消作业',interrupted:'记录中断作业'};
const jobNames = {implement:'实现',review:'只读审查',verify:'定向复验'};
const jobStates = {queued:'排队中',running:'运行中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
let projectId='', projectList=[], csrf='', state=null, ownerFilter='', selected=null, textJob=null, busy=false, loading=false;
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function badge(value,label){return node('span','badge '+value,label||state.labels[value]||value);}
function time(value){return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});}
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
const progressStages = [
  ['todo','待领取'],['in_progress','进行中'],['submitted','待复验'],
  ['rework','返修'],['accepted','已验收'],['integrated','已集成'],['paused','暂停']
];
let progressSignature='';
function buildProgress(tasks,allTasks,jobs){
  const byId=new Map(allTasks.map(t=>[t.id,t]));
  const lanes=progressStages.map(([status,label])=>({status,label,tasks:[]}));
  const finished=t=>Boolean(t&&['accepted','integrated'].includes(t.status));
  let accepted=0,integrated=0,blocked=0;
  for(const task of tasks){
    const dependencies=(task.depends_on||[]).map(id=>({id,task:byId.get(id),ready:finished(byId.get(id))}));
    const waiting=dependencies.filter(d=>!d.ready);
    const active=jobs.filter(j=>j.task_id===task.id&&['queued','running'].includes(j.status))
      .sort((a,b)=>String(b.created).localeCompare(String(a.created)))[0];
    const item={task,dependencies,waiting,active};
    let lane=lanes.find(l=>l.status===task.status);
    if(!lane){lane=lanes.find(l=>l.status==='unknown');if(!lane){lane={status:'unknown',label:'未知状态',tasks:[]};lanes.push(lane);}}
    lane.tasks.push(item);
    if(finished(task))accepted++;
    if(task.status==='integrated')integrated++;
    if(waiting.length&&['todo','rework'].includes(task.status))blocked++;
  }
  for(const lane of lanes)lane.tasks.sort((a,b)=>a.task.id.localeCompare(b.task.id,undefined,{numeric:true}));
  return {lanes,total:tasks.length,accepted,integrated,blocked};
}
function clearProgress(){
  progressSignature='';
  for(const id of ['progress-distribution','progress-legend','progress-board'])$(id).replaceChildren();
  $('progress-scope').textContent='正在加载当前项目…';
  $('progress-summary').textContent='';
  $('task-progress').setAttribute('aria-busy','true');
}
function renderProgress(tasks){
  const signature=JSON.stringify([projectId,ownerFilter,$('search').value,$('status-filter').value,
    state.tasks.map(t=>[t.id,t.title,t.owner,t.status,t.depends_on,t.verification?.passed]),
    state.jobs.filter(j=>['queued','running'].includes(j.status)).map(j=>[j.id,j.task_id,j.kind,j.status])]);
  if(signature===progressSignature)return;
  progressSignature=signature;
  const model=buildProgress(tasks,state.tasks,state.jobs);
  const focus=document.activeElement,focusedTask=focus?.dataset.progressTask,focusedStage=focus?.dataset.progressStage;
  const scrolls=new Map([...document.querySelectorAll('.progress-lane-tasks')].map(e=>[e.dataset.stage,e.scrollTop]));
  const scope=ownerFilter?(names[ownerFilter]||ownerFilter):'全部负责人';
  $('progress-scope').textContent=scope+' · 当前显示 '+model.total+' / '+state.tasks.length+' 项任务';
  $('progress-summary').textContent='已验收（含集成） '+model.accepted+' / '+model.total+' · 已集成 '+model.integrated+' · 等待依赖 '+model.blocked;
  const distribution=$('progress-distribution'),legend=$('progress-legend'),board=$('progress-board');
  distribution.replaceChildren();legend.replaceChildren();board.replaceChildren();
  distribution.setAttribute('aria-label',model.lanes.map(l=>l.label+' '+l.tasks.length+' 项').join('，'));
  for(const lane of model.lanes){
    const pick=()=>{$('status-filter').value=$('status-filter').value===lane.status?'':lane.status;render();};
    const legendButton=button(lane.label+' '+lane.tasks.length,pick);
    legendButton.className='progress-key '+lane.status;
    legendButton.dataset.progressStage=lane.status;
    legendButton.setAttribute('aria-pressed',String($('status-filter').value===lane.status));
    legendButton.title='筛选'+lane.label+'任务，再次点击取消';legend.append(legendButton);
    if(lane.tasks.length){const segment=node('span','progress-segment '+lane.status);segment.style.flexGrow=String(lane.tasks.length);segment.title=lane.label+' '+lane.tasks.length+' 项';distribution.append(segment);}
    const column=node('section','progress-lane '+lane.status);column.setAttribute('aria-label',lane.label+'任务');
    const head=node('h3','progress-lane-title');head.append(node('span','',lane.label),node('span','progress-count',String(lane.tasks.length)));column.append(head);
    const list=node('div','progress-lane-tasks');list.dataset.stage=lane.status;
    for(const item of lane.tasks){
      const t=item.task,card=button('',()=>showTask(t.id));card.className='progress-task';card.dataset.progressTask=t.id;
      card.setAttribute('aria-label',t.id+' '+t.title+'，'+lane.label);
      card.append(node('span','progress-task-id',t.number||t.id),node('span','progress-task-title',t.title),node('span','progress-task-owner',names[t.owner]||t.owner));
      const descriptions=[t.id,t.title,lane.label];
      if(item.waiting.length){const text='等待依赖：'+item.waiting.map(d=>d.task?.number||d.id).join('、');card.append(node('span','progress-waiting',text));descriptions.push(text);}
      else if(item.dependencies.length){card.append(node('span','progress-ready','依赖已验收'));}
      if(item.active){const text=(jobNames[item.active.kind]||item.active.kind)+' · '+jobStates[item.active.status];card.append(node('span','progress-job',text));descriptions.push(text);}
      card.title=descriptions.join('\n');list.append(card);
    }
    if(!lane.tasks.length)list.append(node('p','progress-lane-empty','暂无任务'));
    column.append(list);board.append(column);list.scrollTop=scrolls.get(lane.status)||0;
  }
  if(!model.total)board.append(node('p','progress-empty','没有符合筛选条件的任务；可清除筛选查看全部任务。'));
  $('task-progress').setAttribute('aria-busy','false');
  if(focusedTask){const target=[...board.querySelectorAll('[data-progress-task]')].find(e=>e.dataset.progressTask===focusedTask);(target||$('search')).focus({preventScroll:true});}
  else if(focusedStage){const target=[...legend.querySelectorAll('[data-progress-stage]')].find(e=>e.dataset.progressStage===focusedStage);target?.focus({preventScroll:true});}
}
async function api(path,data){const headers={'X-Coordination-Project':projectId};const options={headers};if(data!==undefined){options.method='POST';headers['Content-Type']='application/json';headers['X-Coordinator-CSRF']=csrf;options.body=JSON.stringify(data);}let r=await fetch(path,options);if(r.status===403&&data!==undefined){const session=await fetch('/api/session');if(session.ok){const fresh=await session.json();csrf=fresh.csrf;headers['X-Coordinator-CSRF']=csrf;r=await fetch(path,options);}}const result=await r.json();if(!r.ok)throw new Error(result.error||'请求失败');return result;}

async function action(path,data){try{busy=true;notice('');const value=await api(path,data);await refresh();return value;}catch(e){notice(e.message);throw e;}finally{busy=false;}}
function button(label,callback,disabled=false){const b=node('button','button',label);b.type='button';b.disabled=disabled;b.addEventListener('click',()=>Promise.resolve(callback()).catch(()=>{}));return b;}
function render(){
  const tasks=state.tasks;$('total').textContent=tasks.length;$('working').textContent=tasks.filter(t=>t.status==='in_progress').length;$('submitted').textContent=tasks.filter(t=>t.status==='submitted').length;$('accepted').textContent=tasks.filter(t=>['accepted','integrated'].includes(t.status)).length;
  const providers=$('providers');providers.replaceChildren();for(const key of ['codex','cursor','claude','lmstudio']){const p=state.providers[key]||{};const card=node('article','provider');card.append(node('div','provider-icon',{codex:'◈',cursor:'↗',claude:'✳',lmstudio:'◎'}[key]));const content=node('div','provider-main');content.append(node('strong','',names[key]),node('p','',p.available?(p.version+' · '+(p.authenticated===false?p.auth:state.connections?.[key]?.passed?'连接已验证':state.connections?.[key]?'连接未通过':'连接待验证')):(p.editor_installed?'编辑器已安装 · Agent CLI未找到':'未检测到可用CLI')));card.append(content,badge(p.available&&p.authenticated!==false?'available':'paused',p.available?(key==='lmstudio'?'仅简单任务':p.authenticated===false?'CLI待授权':'CLI已检测'):'待接入'));providers.append(card);}
  $('automation').checked=state.automation;$('automation-label').textContent=state.automation?'已开启':'已关闭';
  const search=$('search').value.trim().toLowerCase(),status=$('status-filter').value;
  const filtered=tasks.filter(t=>(!ownerFilter||t.owner===ownerFilter)&&(!status||t.status===status)&&(!search||(t.id+' '+t.title+' '+names[t.owner]).toLowerCase().includes(search)));
  const order={in_progress:0,submitted:1,rework:2,todo:3,paused:4,accepted:5,integrated:6};filtered.sort((a,b)=>order[a.status]-order[b.status]||a.id.localeCompare(b.id,undefined,{numeric:true}));
  renderProgress(filtered);
  $('task-count').textContent=filtered.length+' 项';const rows=$('task-rows');rows.replaceChildren();for(const t of filtered){const row=node('tr','task-row');row.tabIndex=0;row.setAttribute('aria-label',t.id+' '+t.title);const title=node('td');title.append(node('div','task-name',t.title),node('div','task-id',t.id));const owner=node('td');owner.append(node('span','owner',names[t.owner]));const status=node('td');status.append(badge(t.status));row.append(title,owner,status,node('td','time',time(t.updated_at)),node('td','','›'));row.addEventListener('click',()=>showTask(t.id));row.addEventListener('keydown',e=>{if(e.key==='Enter')showTask(t.id);});rows.append(row);}$('empty').hidden=filtered.length>0;
  const events=$('events');events.replaceChildren();for(const item of state.events.slice(0,9)){const e=node('div','event');e.append(node('p','',(item.task_id?item.task_id+' · ':'')+(eventNames[item.kind]||item.kind)),node('small','',time(item.at)));events.append(e);}
  const jobs=$('jobs');jobs.replaceChildren();if(!state.jobs.length)jobs.append(node('div','job muted','暂无执行作业。可从任务详情排队实现、发起审查或运行定向复验。'));
  for(const j of state.jobs.slice(0,12)){const e=node('article','job');const title=node('div','job-title',j.task_id+' · '+jobNames[j.kind]);title.append(node('small','',(names[j.provider]||j.provider)+' · '+time(j.created)+(j.data.summary?' · '+j.data.summary:'')));e.append(title,badge(j.status,jobStates[j.status]));e.append(button('查看日志',()=>showLog(j.id)));if(['queued','running'].includes(j.status))e.append(button('取消',()=>action('/api/cancel',{job:j.id})));jobs.append(e);}
  const issues=$('issues');issues.hidden=!state.issues.length;const list=issues.querySelector('ul');list.replaceChildren();for(const issue of state.issues)list.append(node('li','',issue.task+'：'+issue.message));
}
async function refresh(){if(loading||!projectId)return;loading=true;const requestedProject=projectId;try{const incoming=await api('/api/snapshot');if(requestedProject!==projectId)return;state=incoming;render();$('new-task').disabled=false;$('connection').textContent='● 实时连接 · '+new Date().toLocaleTimeString('zh-CN',{hour12:false});if(textJob&&$('text-dialog').open){const r=await api('/api/log/'+textJob);const pre=$('text-content');const end=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-40;pre.textContent=r.text||'等待日志…';if(end)pre.scrollTop=pre.scrollHeight;}}catch(e){$('connection').textContent='连接中断 · 正在重试';notice(e.message);}finally{loading=false;if(requestedProject!==projectId)refresh();}}
function nextNumber(owner){const prefix={cursor:'CR',claude:'C',codex:'CX',deepseek:'D',lmstudio:'LM'}[owner];let i=1;while(state.tasks.some(t=>t.owner===owner&&t.number===prefix+i))i++;return prefix+i;}
function showCreate(){if(!projectId){notice('请先新增项目');return;}const f=$('create-form');f.reset();f.elements.id.value=nextNumber('cursor');f.elements.write_paths.value='cursor-works/src/bootstrap/example.dg\ncursor-works/src/bootstrap/example.md\ncursor-works/tests/test_example.py\ncursor-works/deliveries/'+f.elements.id.value+'.md';$('create-error').textContent='';$('create-dialog').showModal();}
async function showTask(id){selected=id;const t=state.tasks.find(t=>t.id===id);if(!t)return;$('detail-id').textContent=t.id+' · '+names[t.owner];$('detail-title').textContent=t.title;const body=$('detail-body');body.replaceChildren();const meta=node('div','detail-meta');meta.append(badge(t.status),node('span','muted','版本 '+t.rev+(t.historical?' · 历史独立验收':'')));body.append(meta,node('p','',t.description));const errorBox=node('p','');errorBox.id='detail-error';errorBox.setAttribute('role','alert');body.append(errorBox);const docs=node('div','actions');docs.append(button('查看任务书',()=>showDocument(t,'task')),button('查看交付',()=>showDocument(t,'delivery')));body.append(docs,node('h3','','允许修改的文件'),node('div','path-list',t.write_paths.join('\n')),node('h3','','定向测试'),node('div','path-list',t.checks.join('\n')||'尚未配置定向测试'));
  body.append(node('p','progress-position','当前阶段：'+(state.labels[t.status]||t.status)+(t.status==='accepted'?' · 已独立验收，尚未集成':t.status==='submitted'?' · 已提交，等待独立复验':t.status==='rework'?' · 请按审查说明返修':'')));
  if(t.depends_on.length){body.append(node('h3','','前置任务'));const deps=node('div','actions');for(const id of t.depends_on){const dep=state.tasks.find(x=>x.id===id);const b=button(dep?(dep.number+' · '+(state.labels[dep.status]||dep.status)):id+' · 依赖不存在',()=>showTask(id),!dep);b.title=dep?.title||id;deps.append(b);}body.append(deps);}
  if(t.candidate)body.append(node('p','','交付位于当前项目的独立工作副本；原项目文件尚未自动集成。'));
  if(t.verification)body.append(node('p','',t.verification.summary));
  body.append(node('h3','','审查 / 返修说明'));const note=node('textarea','review-note');note.placeholder='记录源码、契约和测试有效性的审查结论；返修时写明具体问题。';note.value=t.review_note||'';body.append(note);const controls=node('div','actions');
  async function change(action,options){await actionRequest('/api/action',{task:t.id,rev:t.rev,action,note:note.value,options});}
  async function queue(kind,provider){await actionRequest('/api/queue',{task:t.id,rev:t.rev,kind,provider});}
  async function actionRequest(path,data){const typed=note.value;let message='';try{await action(path,data);}catch(e){message=e.message;}await refresh();await showTask(t.id);$('detail-body').querySelector('.review-note').value=typed;$('detail-error').textContent=message;}
  const active=state.jobs.some(j=>j.task_id===id&&['queued','running'].includes(j.status));
  if(['todo','rework'].includes(t.status)){controls.append(button('手动领取',()=>change('claim'),active));const p=state.providers[t.owner]||{};controls.append(button('排队执行 CLI',()=>queue('implement'),active||!p.available||!(p.modes||[]).includes('implement')));}
  if(['todo','in_progress','rework'].includes(t.status))controls.append(button('提交主目录交付',()=>change('submit'),active));
  if(t.status==='in_progress')controls.append(button('退回待领取',()=>change('release'),active));if(t.status==='submitted'){controls.append(button('运行定向复验',()=>queue('verify'),active||!t.checks.length));const reviewer=node('select');reviewer.setAttribute('aria-label','审查助手');for(const key of ['codex','claude','cursor']){const op=node('option','',names[key]);op.value=key;op.disabled=!state.providers[key]?.available;reviewer.append(op);}reviewer.value=t.owner==='codex'?'claude':'codex';controls.append(reviewer,button('只读审查',()=>queue('review',reviewer.value),active||!state.providers[reviewer.value]?.available),button('验收通过',()=>change('accept'),active||!t.verification?.passed),button('要求返修',()=>change('rework'),active));}
  if(t.status==='accepted')controls.append(button('确认已集成',()=>change('integrate'),active||!t.verification?.passed),button('要求返修',()=>change('rework'),active));
  if(!['accepted','integrated'].includes(t.status))controls.append(button(t.status==='paused'?'恢复任务':'暂停任务',()=>change(t.status==='paused'?'resume':'pause'),active));body.append(controls);
  if(!['accepted','integrated'].includes(t.status)){const options=node('div','toggle-row');const a=node('label'),b=node('label'),auto=node('input'),verify=node('input');auto.type=verify.type='checkbox';auto.checked=t.auto_dispatch;verify.checked=t.auto_verify;a.append(auto,document.createTextNode(' 自动派单'));b.append(verify,document.createTextNode(' 新交付自动复验'));options.append(a,b);for(const box of [auto,verify]){box.disabled=active;box.addEventListener('change',()=>change('automation',{auto_dispatch:auto.checked,auto_verify:verify.checked}).catch(()=>{}));}body.append(options,node('p','hint','还需开启页面上的自动化总开关。返修不会自动无限重跑；CLI成功与测试通过都不会自动验收。'));}
  if(!$('detail-dialog').open)$('detail-dialog').showModal();
}
async function showDocument(task,kind){textJob=null;try{const r=await api('/api/document?task='+encodeURIComponent(task.id)+'&kind='+kind);$('text-title').textContent=task.id+' · '+(kind==='task'?'任务书':'交付');$('text-content').textContent=r.text;if(!$('text-dialog').open)$('text-dialog').showModal();}catch(e){notice(e.message);}}
async function showLog(id){textJob=id;$('text-title').textContent='执行日志 · '+id.slice(0,8);const r=await api('/api/log/'+id);$('text-content').textContent=r.text||'等待日志…';if(!$('text-dialog').open)$('text-dialog').showModal();}
$('new-task').addEventListener('click',showCreate);for(const [id,dialog]of[['close-create','create-dialog'],['close-detail','detail-dialog'],['close-text','text-dialog']])$(id).addEventListener('click',()=>$(dialog).close());$('text-dialog').addEventListener('close',()=>textJob=null);
document.querySelectorAll('[data-owner]').forEach(b=>b.addEventListener('click',()=>{ownerFilter=b.dataset.owner;document.querySelectorAll('[data-owner]').forEach(x=>x.classList.toggle('selected',x===b));if(state)render();}));for(const id of ['search','status-filter'])$(id).addEventListener('input',()=>state&&render());
$('progress-reset').addEventListener('click',()=>{ownerFilter='';$('search').value='';$('status-filter').value='';document.querySelectorAll('[data-owner]').forEach(b=>b.classList.toggle('selected',!b.dataset.owner));if(state)render();});
$('sync').addEventListener('click',()=>action('/api/sync',{}).catch(()=>{}));$('doctor').addEventListener('click',async()=>{const b=$('doctor');b.disabled=true;b.textContent='正在检测…';try{await action('/api/doctor',{});}catch{}finally{b.disabled=false;b.textContent='重新检测 CLI ↻';}});
$('automation').addEventListener('change',()=>action('/api/automation',{enabled:$('automation').checked}).catch(()=>{}));
$('create-form').elements.owner.addEventListener('change',e=>{const f=$('create-form');f.elements.id.value=nextNumber(e.target.value);f.elements.write_paths.value=e.target.value==='lmstudio'?'lmstudio-works/src/helper.py\nlmstudio-works/deliveries/'+f.elements.id.value+'.md':e.target.value+'-works/src/**\n'+e.target.value+'-works/tests/**\n'+e.target.value+'-works/deliveries/'+f.elements.id.value+'.md';});
$('create-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('[type=submit]');b.disabled=true;$('create-error').textContent='';try{const lines=name=>f.elements[name].value.split('\n').map(x=>x.trim()).filter(Boolean);const task=await api('/api/tasks',{id:f.elements.id.value.trim(),owner:f.elements.owner.value,title:f.elements.title.value.trim(),description:f.elements.description.value,write_paths:lines('write_paths'),checks:lines('checks'),depends_on:f.elements.depends_on.value.split(',').map(x=>x.trim()).filter(Boolean)});if(f.elements.dispatch.checked)await api('/api/queue',{task:task.id,rev:task.rev,kind:'implement'});$('create-dialog').close();await refresh();await showTask(task.id);}catch(error){$('create-error').textContent=error.message;await refresh();}finally{b.disabled=false;}});
async function boot(){try{const session=await api('/api/session');csrf=session.csrf;setProjects(session.projects);await refresh();setInterval(()=>{if(!busy)refresh();},2000);}catch(e){notice(e.message);}}boot();

function setProjects(items,preferred){projectList=items;const existing=preferred||projectId||localStorage.getItem('coordination-project');projectId=items.some(p=>p.id===existing)?existing:(items[0]?.id||'');const select=$('project-select');select.replaceChildren();for(const p of items){const option=node('option','',p.name);option.value=p.id;select.append(option);}if(!items.length)select.append(node('option','','请新增项目'));select.value=projectId;const project=items.find(p=>p.id===projectId);$('project-location').textContent=project?project.works_root:'每个项目的任务、测试、交付和日志集中保存';$('new-task').disabled=!projectId;localStorage.setItem('coordination-project',projectId);}
$('project-select').addEventListener('change',async e=>{if(busy){e.target.value=projectId;return;}projectId=e.target.value;state=null;clearProgress();$('task-rows').replaceChildren();$('jobs').replaceChildren();$('events').replaceChildren();$('new-task').disabled=true;ownerFilter='';$('search').value='';$('status-filter').value='';for(const dialog of document.querySelectorAll('dialog'))dialog.close();document.querySelectorAll('[data-owner]').forEach(b=>b.classList.toggle('selected',!b.dataset.owner));const activeProject=projectList.find(p=>p.id===projectId);$('project-location').textContent=activeProject?.works_root||'';localStorage.setItem('coordination-project',projectId);await refresh();});
$('new-project').addEventListener('click',()=>{$('project-form').reset();$('project-error').textContent='';$('project-dialog').showModal();});
$('close-project').addEventListener('click',()=>$('project-dialog').close());
$('project-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('[type=submit]');b.disabled=true;try{const item=await api('/api/projects',{id:f.elements.id.value.trim(),name:f.elements.name.value.trim(),source_root:f.elements.source_root.value.trim()});setProjects(await api('/api/projects'),item.id);$('project-dialog').close();await refresh();}catch(error){$('project-error').textContent=error.message;}finally{b.disabled=false;}});
document.querySelector('a[href="/api/export"]').addEventListener('click',async e=>{e.preventDefault();const data=await api('/api/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=projectId+'-tasks.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
