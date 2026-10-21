'use strict';
const $ = id => document.getElementById(id);
const names = {unassigned:'公共任务池',codex:'Codex',cursor:'Cursor',claude:'Claude',deepseek:'DeepSeek',lmstudio:'LM Studio',python:'Python'};
const icons = {unassigned:'○',codex:'◈',cursor:'↗',claude:'✳',deepseek:'◇',lmstudio:'◎'};
const members = ['codex','cursor','claude','deepseek','lmstudio'];
const eventNames = {pause_requested:'请求暂停，等待停止确认',stopped:'执行器已停止',acknowledge_pause:'领取者确认已停止',confirm_pause:'用户确认已停止',assignment_changed:'记录转派交接',reassign:'转派任务',release:'释放任务',imported:'导入历史任务',created:'发布任务',claim:'领取任务',started:'CLI开始执行',submit:'提交交付',queued:'加入执行队列',verified:'完成定向复验',accept:'独立验收通过',integrate:'确认集成',rework:'要求返修',document_changed:'任务书更新',job_finished:'作业结束',pause:'暂停任务',resume:'恢复任务',automation:'更新自动化设置',implementation_finished:'收集实现结果',cancel_requested:'请求取消作业',interrupted:'记录中断作业',verification_started:'开始定向复验',archive:'归档',unarchive:'恢复归档'};
const jobNames = {implement:'实现',review:'只读审查',verify:'定向复验'};
const jobStates = {queued:'排队中',running:'运行中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
const DONE = ['accepted','integrated'];
const pages = {
  overview:['概览','任务进展、待处理事项和成员负载一览。'],
  tasks:['任务','按成员、状态和关键词筛选；点击任务在右侧查看详情并操作。'],
  roadmap:['整体任务图','项目阶段、验收依据与剩余工作。'],
  runtime:['执行与环境','CLI 接入、自动化开关与执行队列日志。'],
  activity:['动态','全部任务操作记录，最新在前。'],
};
let listPage=0, documentRequest=0, pageSize=20;
let projectId='', projectList=[], csrf='', state=null, ownerFilter='', statusFilter='', sortOrder='status', jobFilter='', selected=null, textJob=null, busy=false, loading=false;
let visibleIds=[], expandedDescription=null;
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function badge(value,label){return node('span','badge '+value,label||state.labels[value]||value);}
function time(value){if(!value)return '未知';return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});}
function ago(value){
  if(!value)return '—';const at=new Date(value).getTime();if(Number.isNaN(at))return '—';
  const s=Math.max(0,(Date.now()-at)/1000);
  return s<60?'刚刚':s<3600?Math.floor(s/60)+' 分钟前':s<86400?Math.floor(s/3600)+' 小时前':s<86400*7?Math.floor(s/86400)+' 天前':time(value);
}
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
function duration(value){if(value===null||value===undefined)return '未知';const n=Math.floor(value);return (n>=3600?Math.floor(n/3600)+'小时':'')+(n>=60?Math.floor(n%3600/60)+'分':'')+(n%60)+'秒';}
function exactTime(value){return value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未知';}
function ownerName(task){return task.owner?((names[task.owner]||task.owner)+(!task.claimed_by&&['todo','rework'].includes(task.status)?' · 待领取':'')):'待领取 · 公共任务';}
function latestRound(task){return task.timing?.latest_round||task.timing?.rounds?.at(-1)||null;}
function taskElapsed(task){const round=latestRound(task);return round?duration(round.elapsed_seconds):'—';}
function elapsedLabel(task){const round=latestRound(task);return !round?'暂无领取记录':round.ongoing?'本轮进行中':round.submitted_at?'执行完成（提交）':'本轮已结束 · 未提交';}
function byNumber(a,b){return a.id.localeCompare(b.id,undefined,{numeric:true});}
function statusMatches(task,status){return !status||(status==='active'?!DONE.includes(task.status):task.status===status);}
function ownerMatches(task,owner){return !owner||task.owner===owner||owner==='unassigned'&&!task.owner;}
function activeJob(taskId){return state.jobs.filter(j=>j.task_id===taskId&&['queued','running'].includes(j.status)).sort((a,b)=>String(b.created).localeCompare(String(a.created)))[0];}
function waitingDeps(task){return (task.depends_on||[]).filter(id=>{const dep=state.tasks.find(x=>x.id===id);return !dep||!DONE.includes(dep.status);});}
function shortId(id){const dep=state.tasks.find(x=>x.id===id);return dep?.number||id;}
// Rebuild a container from scratch while keeping keyboard focus on the same logical item.
function rebuild(container,fill){
  const key=document.activeElement?.dataset?.focusKey;container.replaceChildren();fill(container);
  if(key){const target=[...container.querySelectorAll('[data-focus-key]')].find(e=>e.dataset.focusKey===key);target?.focus({preventScroll:true});}
}
function metric(label,value,cls=''){const item=node('div','timing-metric '+cls);item.append(node('span','',label),node('strong','',value));return item;}
function renderTaskMetrics(task){
  const panel=node('div','task-metrics'),round=latestRound(task);
  panel.append(metric('领取成员',round?.owner?(names[round.owner]||round.owner)+(task.claimed_at?'':'（上轮）'):task.claimed_by?ownerName(task):'暂无领取记录'),metric('本轮领取 · 北京时间',exactTime(round?.claimed_at)),
    metric('执行完成（提交）',round?.submitted_at?exactTime(round.submitted_at):round?.ongoing?'等待提交':'暂无记录'),
    metric('本轮经过时长',taskElapsed(task),'elapsed-metric'));
  return panel;
}
function renderTiming(body,t){
  const data=t.timing;if(!data)return;
  body.append(node('h3','','时间记录（北京时间）'));
  const summary=node('div','path-list');summary.textContent=[
    '发布：'+exactTime(data.published_at),'首次领取：'+exactTime(data.first_claimed_at),
    '最近执行完成（提交）：'+exactTime(data.last_submitted_at),'最近复验完成：'+exactTime(data.last_verified_at),
    '最近要求返修：'+exactTime(data.last_rework_requested_at),
    '任务书最近修改：'+exactTime(data.last_modified_at),'状态最近更新：'+exactTime(t.updated_at),
    '累计办理：'+duration(data.total_active_seconds),'其中返修：'+duration(data.rework_active_seconds)].join('\n');body.append(summary);
  body.append(node('p','hint',data.duration_basis+'。提交完成与验收、集成分别记录；任务书修改时间不代表源码编辑时间。'+(data.history_incomplete?'历史记录不完整，缺失时间不补造。':'')));
  for(const r of data.rounds){body.append(node('p','',`第${r.number}轮${r.kind==='rework'?'返修':'实现'}：${exactTime(r.claimed_at)} → ${r.ongoing?'进行中':exactTime(r.ended_at)} · 经过 ${duration(r.elapsed_seconds)} · 办理 ${duration(r.active_seconds)} · 暂停 ${duration(r.paused_seconds)} · 等待领取 ${duration(r.waiting_seconds)}${r.end_reason&&!r.submitted_at?' · 未提交结束':''}`));}
  for(const v of data.verifications||[]){body.append(node('p','',`复验 ${v.id.slice(0,8)}：排队 ${exactTime(v.queued_at)} · 开始 ${exactTime(v.started_at)} · 结束 ${exactTime(v.finished_at)} · ${jobStates[v.status]||v.status} · 执行 ${duration(v.elapsed_seconds)} · 测试合计 ${duration(v.check_seconds)}`));}
  const details=node('details');details.append(node('summary','','完整操作时间线'));for(const e of data.timeline){details.append(node('p','',exactTime(e.at)+' · '+(eventNames[e.kind]||e.kind)+(e.data?.status?' · '+(state.labels[e.data.status]||e.data.status):'')));}body.append(details);
}
const roadmapStatuses={complete:'✓ 已通过验收',partial:'◐ 部分完成',pending:'○ 尚未完成'};
let roadmapSignature='',roadmapSelection='';
function clearRoadmap(){
  roadmapSignature='';roadmapSelection='';
  $('roadmap-title').textContent='整体任务图';$('roadmap-meta').textContent='正在加载当前项目…';
  for(const id of ['roadmap-summary','roadmap-focus','roadmap-task-summary'])$(id).textContent='';
  for(const id of ['roadmap-tracks','roadmap-detail','roadmap-notes','overview-roadmap'])$(id).replaceChildren();
  $('roadmap-detail').hidden=true;$('roadmap-download').disabled=true;
  $('project-roadmap').setAttribute('aria-busy','true');
}
function selectRoadmapStage(key){
  const map=state?.roadmap;if(!map)return;
  const entries=map.tracks.flatMap(track=>track.stages.map(stage=>({track,stage,key:track.id+':'+stage.id})));
  const entry=entries.find(item=>item.key===key);if(!entry)return;
  roadmapSelection=key;
  for(const button of $('roadmap-tracks').querySelectorAll('[data-roadmap-stage]'))button.setAttribute('aria-pressed',String(button.dataset.roadmapStage===key));
  const {stage}=entry,detail=$('roadmap-detail');detail.replaceChildren();detail.hidden=false;
  const heading=node('div','roadmap-detail-heading');heading.append(node('h3','',stage.id+' · '+stage.title),node('span','roadmap-status '+stage.status,roadmapStatuses[stage.status]));detail.append(heading);
  const columns=node('div','roadmap-detail-columns');
  const complete=stage.status==='complete'&&stage.remaining.length===0;
  for(const [title,items,empty] of [['已完成',stage.done,'尚无已验收项目'],[complete?'验收结论':'尚待完成',stage.remaining,complete?'本项既定范围内无待办，已通过验收':'尚未列出具体验收待办']]){
    const section=node('div');section.append(node('h4','',title));
    if(items.length){const list=node('ul');for(const text of items)list.append(node('li','',text));section.append(list);}else section.append(node('p','',empty));
    columns.append(section);
  }
  detail.append(columns);
  if(stage.scope_notes?.length){const scope=node('section','roadmap-detail-scope');scope.append(node('h4','','验收范围与后续归属'));const list=node('ul');for(const text of stage.scope_notes)list.append(node('li','',text));scope.append(list);detail.append(scope);}
  if(stage.evidence.length){const sources=node('div','roadmap-evidence');sources.append(node('span','','核对依据：'));for(const reference of stage.evidence)sources.append(node('code','',reference));detail.append(sources);}
}
function renderRoadmap(){
  const tasks=state.tasks,integrated=tasks.filter(t=>t.status==='integrated').length,accepted=tasks.filter(t=>t.status==='accepted').length;
  $('roadmap-task-summary').textContent='实时协作任务 '+tasks.length+' 项 · 已集成 '+integrated+' · 已验收未集成 '+accepted+' · 未验收 '+(tasks.length-integrated-accepted);
  const map=state.roadmap,signature=JSON.stringify([projectId,map,state.roadmap_error]);
  if(signature===roadmapSignature)return;roadmapSignature=signature;
  const tracks=$('roadmap-tracks'),notes=$('roadmap-notes');tracks.replaceChildren();notes.replaceChildren();
  $('roadmap-detail').hidden=true;$('roadmap-detail').replaceChildren();$('roadmap-download').disabled=!map;
  $('project-roadmap').setAttribute('aria-busy','false');
  renderRoadmapMini(map);
  if(!map){
    $('roadmap-title').textContent='整体任务图';$('roadmap-meta').textContent=state.roadmap_error?'任务图暂不可用：'+state.roadmap_error:'当前项目尚未保存整体任务图。';
    $('roadmap-summary').textContent='';$('roadmap-focus').textContent='';roadmapSelection='';return;
  }
  $('roadmap-title').textContent=map.title;
  const checked=new Date(map.updated_at);$('roadmap-meta').textContent='阶段核对于 '+(Number.isNaN(checked.getTime())?map.updated_at:checked.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}))+'（北京时间） · '+map.scope;
  $('roadmap-summary').textContent=map.summary;$('roadmap-focus').textContent=map.focus;
  for(const track of map.tracks){
    const section=node('section','roadmap-track');section.dataset.track=track.id;section.append(node('h3','',track.title));const list=node('ol','roadmap-flow');
    for(const stage of track.stages){
      const item=node('li'),key=track.id+':'+stage.id,control=button('',()=>selectRoadmapStage(key));control.className='roadmap-stage '+stage.status;
      control.dataset.roadmapStage=key;control.setAttribute('aria-pressed','false');control.setAttribute('aria-controls','roadmap-detail');
      control.append(node('span','roadmap-stage-id',stage.id),node('strong','roadmap-stage-title',stage.title),node('span','roadmap-status '+stage.status,roadmapStatuses[stage.status]));
      item.append(control);list.append(item);
    }
    section.append(list);tracks.append(section);
  }
  if(map.notes.length){notes.append(node('summary','','范围与证据说明'));for(const text of map.notes)notes.append(node('p','',text));}
  const all=map.tracks.flatMap(track=>track.stages.map(stage=>({stage,key:track.id+':'+stage.id})));
  const initial=all.find(item=>item.key===roadmapSelection)||all.find(item=>item.stage.id==='L3')||all.find(item=>item.stage.status==='partial')||all[0];
  if(initial)selectRoadmapStage(initial.key);
}
// Compact stage strip on the overview; clicking a stage opens it on the roadmap page.
function renderRoadmapMini(map){
  const box=$('overview-roadmap');box.replaceChildren();
  if(!map){box.append(node('p','empty-note',state.roadmap_error?'任务图暂不可用：'+state.roadmap_error:'当前项目尚未保存整体任务图。'));return;}
  if(map.focus)box.append(node('p','mini-roadmap-focus',map.focus));
  for(const track of map.tracks){
    const row=node('div','mini-track'),counts={complete:0,partial:0,pending:0};
    for(const stage of track.stages)counts[stage.status]=(counts[stage.status]||0)+1;
    const head=node('div','mini-track-head');head.append(node('strong','',track.title),node('span','muted','完成 '+counts.complete+' · 部分 '+counts.partial+' · 未开始 '+counts.pending));row.append(head);
    const stages=node('div','mini-stages');
    for(const stage of track.stages){
      const key=track.id+':'+stage.id,pill=button('',()=>{go('roadmap');selectRoadmapStage(key);});
      pill.className='mini-stage '+stage.status;pill.title=stage.id+' · '+stage.title+' · '+roadmapStatuses[stage.status];
      pill.append(node('span','mini-stage-id',stage.id),node('span','mini-stage-title',stage.title));stages.append(pill);
    }
    row.append(stages);box.append(row);
  }
}
async function downloadRoadmap(){
  const requestedProject=projectId;
  try{
    const response=await fetch('/api/roadmap?format=markdown',{headers:{'X-Coordination-Project':requestedProject}});
    if(!response.ok){const error=await response.json();throw new Error(error.error||'任务图下载失败');}
    const text=await response.text(),url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));
    const link=node('a');link.href=url;link.download=requestedProject+'-progress-map.md';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(error){notice(error.message);}
}
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
  for(const id of ['progress-distribution','progress-board','overview-distribution','overview-legend'])$(id).replaceChildren();
  $('progress-scope').textContent='正在加载当前项目…';
  $('progress-summary').textContent='';
  $('task-progress').setAttribute('aria-busy','true');
}
function fillDistribution(element,lanes){
  element.replaceChildren();
  element.setAttribute('aria-label',lanes.map(l=>l.label+' '+l.tasks.length+' 项').join('，'));
  for(const lane of lanes)if(lane.tasks.length){const segment=node('span','progress-segment '+lane.status);segment.style.flexGrow=String(lane.tasks.length);segment.title=lane.label+' '+lane.tasks.length+' 项';element.append(segment);}
}
function renderProgress(tasks){
  const signature=JSON.stringify([projectId,ownerFilter,$('search').value,statusFilter,
    state.tasks.map(t=>[t.id,t.rev,t.title,t.owner,t.status,t.depends_on,t.verification?.passed]),
    state.jobs.filter(j=>['queued','running'].includes(j.status)).map(j=>[j.id,j.task_id,j.kind,j.status])]);
  if(signature===progressSignature)return;
  progressSignature=signature;
  const model=buildProgress(tasks,state.tasks,state.jobs);
  const focus=document.activeElement,focusedTask=focus?.dataset.progressTask;
  const scrolls=new Map([...document.querySelectorAll('.progress-lane-tasks')].map(e=>[e.dataset.stage,e.scrollTop]));
  const scope=ownerFilter?(names[ownerFilter]||ownerFilter):'全部负责人';
  $('progress-scope').textContent=scope+' · 当前显示 '+model.total+' / '+state.tasks.length+' 项';
  $('progress-summary').textContent='已验收（含集成） '+model.accepted+' · 已集成 '+model.integrated+' · 等待依赖 '+model.blocked;
  const board=$('progress-board');board.replaceChildren();
  fillDistribution($('progress-distribution'),model.lanes);
  for(const lane of model.lanes){
    if(statusFilter&&!lane.tasks.length)continue;
    const column=node('section','progress-lane '+lane.status);column.setAttribute('aria-label',lane.label+'任务');
    const head=node('h3','progress-lane-title');head.append(node('span','',lane.label),node('span','progress-count',String(lane.tasks.length)));column.append(head);
    const list=node('div','progress-lane-tasks');list.dataset.stage=lane.status;
    for(const item of lane.tasks){
      const t=item.task,card=button('',()=>showTask(t.id));card.className='progress-task';card.dataset.progressTask=t.id;
      card.setAttribute('aria-label',t.id+' '+t.title+'，'+lane.label);
      card.append(node('span','progress-task-id',t.number||t.id),node('span','progress-task-title',t.title),node('span','progress-task-owner',ownerName(t)));
      const clock=node('span','progress-task-time',taskElapsed(t));clock.dataset.taskClock=t.id;clock.title=elapsedLabel(t);card.append(clock);
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
}
async function api(path,data){const headers={'X-Coordination-Project':projectId};const options={headers};if(data!==undefined){options.method='POST';headers['Content-Type']='application/json';headers['X-Coordinator-CSRF']=csrf;options.body=JSON.stringify(data);}let r=await fetch(path,options);if(r.status===403&&data!==undefined){const session=await fetch('/api/session');if(session.ok){const fresh=await session.json();csrf=fresh.csrf;headers['X-Coordinator-CSRF']=csrf;r=await fetch(path,options);}}const result=await r.json();if(!r.ok)throw new Error(result.error||'请求失败');return result;}

async function action(path,data){try{busy=true;notice('');const value=await api(path,data);await refresh();return value;}catch(e){notice(e.message);throw e;}finally{busy=false;}}
function button(label,callback,disabled=false){const b=node('button','button',label);b.type='button';b.disabled=disabled;b.addEventListener('click',async()=>{if(b.disabled)return;b.disabled=true;try{await callback();}catch{}finally{if(b.isConnected)b.disabled=disabled;}});return b;}

// ---- Page routing --------------------------------------------------------
function go(page,{push=true}={}){
  if(!pages[page])page='overview';
  document.body.dataset.page=page;
  document.querySelectorAll('[data-page-link]').forEach(a=>a.setAttribute('aria-current',a.dataset.pageLink===page?'page':'false'));
  $('page-title').textContent=pages[page][0];$('page-subtitle').textContent=pages[page][1];
  const project=projectList.find(p=>p.id===projectId);
  $('page-eyebrow').textContent=(project?.name||'WORKSPACE').toUpperCase()+' / '+page.toUpperCase();
  document.title=pages[page][0]+' · '+(project?.name||'协作工作台');
  if(push&&location.hash.slice(1)!==page)location.hash=page;
}
function showTasks(status,owner){
  if(status!==undefined)statusFilter=status;
  if(owner!==undefined){ownerFilter=owner;syncOwnerNav();}
  listPage=0;go('tasks');if(state)render();
}
function syncOwnerNav(){document.querySelectorAll('[data-owner]').forEach(b=>b.classList.toggle('selected',Boolean(ownerFilter)&&b.dataset.owner===ownerFilter));}

// ---- Overview ------------------------------------------------------------
function countBy(tasks){const counts={};for(const t of tasks)counts[t.status]=(counts[t.status]||0)+1;return counts;}
function laneModel(tasks){const counts=countBy(tasks);return progressStages.map(([status,label])=>({status,label,tasks:{length:counts[status]||0}}));}
function attentionGroups(){
  const tasks=state.tasks,groups=[];
  const add=(key,title,hint,items,extra,jump)=>{if(items.length)groups.push({key,title,hint,items:items.sort(byNumber),extra,jump});};
  add('stopping','等待停止确认','暂停请求尚未确认，确认前不能转派',tasks.filter(t=>t.pause_requested_at),t=>t.pause_control==='managed'?'正在停止执行器':'等待外部确认','');
  add('submitted','待复验 / 待验收','交付已提交，需要定向复验和审查',tasks.filter(t=>t.status==='submitted'),t=>t.verification?(t.verification.passed?'复验通过 · 待验收':'复验未通过'):'尚未复验','submitted');
  add('rework','返修中','审查退回，等待原负责人修改',tasks.filter(t=>t.status==='rework'),t=>t.claimed_by?'已重新领取':'待重新领取','rework');
  add('in_progress','进行中','已领取，等待提交',tasks.filter(t=>t.status==='in_progress'&&!t.pause_requested_at),t=>'经过 '+taskElapsed(t),'in_progress');
  const todo=tasks.filter(t=>t.status==='todo');
  add('ready','可领取','依赖已全部验收',todo.filter(t=>!waitingDeps(t).length),t=>t.owner?names[t.owner]||t.owner:'公共任务','todo');
  add('blocked','等待依赖','前置任务尚未验收',todo.filter(t=>waitingDeps(t).length),t=>'等待 '+waitingDeps(t).map(shortId).join('、'),'todo');
  add('integrate','已验收 · 待集成','核对源码集成后登记',tasks.filter(t=>t.status==='accepted'),()=>'待集成登记','accepted');
  add('paused','暂停','可恢复或转派',tasks.filter(t=>t.status==='paused'&&!t.pause_requested_at),t=>t.resume_status==='rework'?'恢复后为返修':'可恢复','paused');
  return groups;
}
function renderOverview(){
  const tasks=state.tasks,counts=countBy(tasks),done=(counts.accepted||0)+(counts.integrated||0);
  $('total').textContent=tasks.length;$('working').textContent=counts.in_progress||0;$('submitted').textContent=counts.submitted||0;
  $('rework').textContent=counts.rework||0;$('accepted').textContent=done;
  $('total-note').textContent='未完成 '+(tasks.length-done)+' · 待领取 '+(counts.todo||0)+(counts.paused?' · 暂停 '+counts.paused:'');
  $('accepted-note').textContent=tasks.length?'占 '+Math.round(done*100/tasks.length)+'% · 已集成 '+(counts.integrated||0):'独立验收与集成分别记录';
  const lanes=laneModel(tasks);fillDistribution($('overview-distribution'),lanes);
  rebuild($('overview-legend'),legend=>{for(const lane of lanes){if(!lane.tasks.length)continue;const key=button('',()=>showTasks(lane.status,''));key.className='legend-key '+lane.status;key.dataset.focusKey='legend:'+lane.status;key.append(node('span','legend-label',lane.label),node('strong','',String(lane.tasks.length)));legend.append(key);}});
  const groups=attentionGroups();
  rebuild($('attention-list'),list=>{
    if(!groups.length){list.append(node('p','empty-note','暂无待处理任务。'));return;}
    for(const group of groups){
      const section=node('section','attention-group '+group.key),head=node('div','attention-head');
      head.append(node('strong','',group.title),node('span','attention-count',String(group.items.length)),node('span','muted',group.hint));
      if(group.jump&&group.items.length>4){const more=button('全部 '+group.items.length+' 项 ›',()=>showTasks(group.jump,''));more.className='link';more.dataset.focusKey='more:'+group.key;head.append(more);}
      section.append(head);
      for(const t of group.items.slice(0,4)){
        const row=button('',()=>showTask(t.id));row.className='attention-item';row.dataset.focusKey='att:'+group.key+':'+t.id;row.title=t.id+' · '+t.title;
        row.append(node('span','attention-id',t.number||t.id),node('span','attention-title',t.title),node('span','attention-extra',group.extra(t)));
        section.append(row);
      }
      list.append(section);
    }
  });
  $('nav-count-overview').textContent=String(groups.filter(g=>['stopping','submitted','rework'].includes(g.key)).reduce((n,g)=>n+g.items.length,0)||'');
  rebuild($('member-cards'),box=>{
    for(const key of ['unassigned',...members]){
      const own=tasks.filter(t=>ownerMatches(t,key));if(key==='unassigned'&&!own.length)continue;
      const c=countBy(own),finished=(c.accepted||0)+(c.integrated||0),p=state.providers?.[key];
      const card=button('',()=>showTasks('active',key));card.className='member-card';card.dataset.focusKey='member:'+key;
      const head=node('div','member-head');head.append(node('span','member-icon',icons[key]||'•'),node('strong','',names[key]||key));
      if(p)head.append(node('span','member-cli '+(p.available&&p.authenticated!==false?'on':'off'),p.available?(p.authenticated===false?'CLI待授权':'CLI可用'):'未接入CLI'));
      const numbers=node('div','member-numbers');
      for(const [status,label] of [['in_progress','进行中'],['submitted','待复验'],['rework','返修'],['todo','待领取']]){const item=node('span','member-number '+status+(c[status]?'':' zero'));item.append(node('b','',String(c[status]||0)),node('small','',label));numbers.append(item);}
      const bar=node('div','progress-distribution slim');fillDistribution(bar,laneModel(own));
      card.append(head,numbers,bar,node('small','member-foot','已完成 '+finished+' / '+own.length+' 项'));box.append(card);
    }
  });
}
function jobRow(j,compact){
  const e=node('article','job '+j.status);const title=node('div','job-title');
  const link=button(j.task_id,()=>showTask(j.task_id));link.className='link job-task';
  title.append(link,node('span','job-kind',' · '+(jobNames[j.kind]||j.kind)),node('small','',(names[j.provider]||j.provider)+' · '+time(j.created)+(j.data?.summary?' · '+j.data.summary:'')));
  e.append(title,badge(j.status,jobStates[j.status]||j.status),button(compact?'日志':'查看日志',()=>showLog(j.id)));
  if(['queued','running'].includes(j.status))e.append(button('取消',()=>action('/api/cancel',{job:j.id})));
  return e;
}
function eventText(item){
  const parts=[eventNames[item.kind]||item.kind];
  if(item.data?.status&&item.kind!=='job_finished')parts.push(state.labels[item.data.status]||item.data.status);
  if(item.kind==='job_finished'&&item.data?.status)parts.push(jobStates[item.data.status]||item.data.status);
  if(item.kind==='automation')parts.push(item.data?.enabled?'开启':'关闭');
  return parts.join(' · ');
}
function eventRow(item,key){
  const e=node('div','event');
  if(item.task_id){const link=button(shortId(item.task_id),()=>showTask(item.task_id),!state.tasks.some(t=>t.id===item.task_id));link.className='link event-task';link.title=item.task_id;link.dataset.focusKey=key;e.append(link);}
  e.append(node('p','',eventText(item)));const at=node('small','',ago(item.at));at.title=exactTime(item.at);e.append(at);
  return e;
}
function renderOverviewFeeds(){
  const active=state.jobs.filter(j=>['queued','running'].includes(j.status)),recent=active.length?active:state.jobs.slice(0,4);
  rebuild($('overview-jobs'),box=>{
    if(!state.jobs.length){box.append(node('p','empty-note','暂无执行作业。可从任务详情排队实现、发起审查或运行定向复验。'));return;}
    if(!active.length)box.append(node('p','mini-caption','当前没有排队或运行中的作业 · 最近记录：'));
    for(const j of recent.slice(0,6))box.append(jobRow(j,true));
  });
  rebuild($('overview-events'),box=>{
    if(!state.events.length){box.append(node('p','empty-note','暂无动态。'));return;}
    state.events.slice(0,8).forEach((item,i)=>box.append(eventRow(item,'oev:'+i)));
  });
}

// ---- Runtime & activity --------------------------------------------------
function renderRuntime(){
  rebuild($('providers'),providers=>{for(const key of ['codex','cursor','claude','lmstudio']){const p=state.providers[key]||{};const card=node('article','provider');card.append(node('div','provider-icon',icons[key]));const content=node('div','provider-main');content.append(node('strong','',names[key]),node('p','',p.available?(p.version+' · '+(p.authenticated===false?p.auth:state.connections?.[key]?.passed?'连接已验证':state.connections?.[key]?'连接未通过':'连接待验证')):(p.editor_installed?'编辑器已安装 · Agent CLI未找到':'未检测到可用CLI')));card.append(content,badge(p.available&&p.authenticated!==false?'available':'paused',p.available?(key==='lmstudio'?'仅简单任务':p.authenticated===false?'CLI待授权':'CLI已检测'):'待接入'));providers.append(card);}});
  $('automation').checked=state.automation;$('automation-label').textContent=state.automation?'已开启':'已关闭';
  const active=state.jobs.filter(j=>['queued','running'].includes(j.status)),running=active.filter(j=>j.status==='running').length;
  $('nav-count-runtime').textContent=active.length?String(active.length):'';
  $('jobs-active').hidden=!active.length;
  $('jobs-summary').textContent=active.length?`运行中 ${running} · 排队 ${active.length-running} · 共 ${state.jobs.length} 条记录`:(state.jobs.length?`无运行作业 · 共 ${state.jobs.length} 条记录`:'暂无执行作业');
  const jobs=state.jobs.filter(j=>!jobFilter||(jobFilter==='active'?['queued','running'].includes(j.status):['failed','interrupted'].includes(j.status)));
  $('job-count').textContent=jobs.length+' 项';
  document.querySelectorAll('[data-job-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.jobFilter===jobFilter)));
  rebuild($('jobs'),box=>{
    if(!jobs.length)box.append(node('div','job muted',state.jobs.length?'没有符合筛选的作业。':'暂无执行作业。可从任务详情排队实现、发起审查或运行定向复验。'));
    for(const j of jobs)box.append(jobRow(j,false));
  });
}
function renderActivity(){
  const query=$('event-search').value.trim().toLowerCase();
  const items=state.events.filter(item=>!query||((item.task_id||'')+' '+eventText(item)).toLowerCase().includes(query));
  $('event-count').textContent=items.length+' / '+state.events.length+' 条';
  rebuild($('events'),box=>{
    if(!items.length){box.append(node('p','empty-note',state.events.length?'没有符合筛选的动态。':'暂无动态。'));return;}
    let day='';
    items.forEach((item,i)=>{
      const label=item.at?new Date(item.at).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'short'}):'未知日期';
      if(label!==day){day=label;box.append(node('h3','event-day',label));}
      const row=eventRow(item,'ev:'+i);const at=row.querySelector('small');if(at){at.textContent=new Date(item.at).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});}
      box.append(row);
    });
  });
}

// ---- Task list -----------------------------------------------------------
const statusOrder={in_progress:0,submitted:1,rework:2,todo:3,paused:4,accepted:5,integrated:6};
const sorters={
  status:(a,b)=>(statusOrder[a.status]??9)-(statusOrder[b.status]??9)||byNumber(a,b),
  id:byNumber,
  updated:(a,b)=>String(b.updated_at||'').localeCompare(String(a.updated_at||''))||byNumber(a,b),
  elapsed:(a,b)=>(latestRound(b)?.elapsed_seconds??-1)-(latestRound(a)?.elapsed_seconds??-1)||byNumber(a,b),
};
function render(){
  const tasks=state.tasks;
  renderOverview();renderOverviewFeeds();renderRoadmap();renderRuntime();renderActivity();
  for(const span of document.querySelectorAll('[data-owner-count]')){const n=tasks.filter(t=>ownerMatches(t,span.dataset.ownerCount)&&!DONE.includes(t.status)).length;span.textContent=n?String(n):'';}
  $('nav-count-tasks').textContent=String(tasks.filter(t=>!DONE.includes(t.status)).length||'');
  const search=$('search').value.trim().toLowerCase();
  const scoped=tasks.filter(t=>ownerMatches(t,ownerFilter)&&(!search||(t.id+' '+t.title+' '+ownerName(t)+' '+(t.claimed_by||'')).toLowerCase().includes(search)));
  const counts=countBy(scoped);
  for(const span of document.querySelectorAll('[data-count]')){const key=span.dataset.count;span.textContent=String(key===''?scoped.length:key==='active'?scoped.filter(t=>!DONE.includes(t.status)).length:counts[key]||0);}
  const filtered=scoped.filter(t=>statusMatches(t,statusFilter)).sort(sorters[sortOrder]||sorters.status);
  visibleIds=filtered.map(t=>t.id);
  renderProgress(filtered);
  $('owner-filter').value=ownerFilter;
  document.querySelectorAll('[data-quick]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.quick===statusFilter)));
  listPage=Math.min(listPage,Math.max(0,Math.ceil(filtered.length/pageSize)-1));
  const page=filtered.slice(listPage*pageSize,(listPage+1)*pageSize),rows=$('task-rows');
  const focusedId=document.activeElement?.dataset.taskRow;
  rows.replaceChildren();
  for(const t of page){
    const row=node('tr','task-row'+(t.id===selected?' current':''));row.tabIndex=0;row.dataset.taskRow=t.id;row.setAttribute('aria-label',t.id+' '+t.title);
    const title=node('td'),meta=node('div','task-meta');meta.append(node('span','task-id',t.id));
    const waiting=['todo','rework'].includes(t.status)?waitingDeps(t):[];
    if(waiting.length)meta.append(node('span','row-tag waiting','等待 '+waiting.map(shortId).join('、')));
    const job=activeJob(t.id);if(job)meta.append(node('span','row-tag job',(jobNames[job.kind]||job.kind)+' · '+jobStates[job.status]));
    if(t.status==='submitted'&&t.verification)meta.append(node('span','row-tag '+(t.verification.passed?'passed':'failed'),t.verification.passed?'复验通过':'复验未通过'));
    title.append(node('div','task-name',t.title),meta);
    const owner=node('td');owner.append(node('span','owner'+(!t.owner?' unassigned':''),ownerName(t)));
    if(t.claimed_by){const claimant=node('small','claimant',t.claimed_by);claimant.title=t.claimed_by;owner.append(claimant);}
    const status=node('td');status.append(badge(t.status));if(t.pause_requested_at)status.append(node('small','stopping-status',t.pause_control==='managed'?'正在停止执行器…':'等待停止确认'));
    const elapsed=node('td','elapsed');elapsed.append(node('strong','',taskElapsed(t)),node('small','',elapsedLabel(t)));elapsed.title=latestRound(t)?exactTime(latestRound(t).claimed_at)+' → '+(latestRound(t).ongoing?'进行中':exactTime(latestRound(t).ended_at)): '历史缺失时不补造时间';
    const updated=node('td','updated',ago(t.updated_at));updated.title=exactTime(t.updated_at);
    row.append(title,status,owner,elapsed,updated,node('td','chevron','›'));
    row.addEventListener('click',()=>showTask(t.id));row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showTask(t.id);}});rows.append(row);
  }
  if(focusedId)[...rows.children].find(e=>e.dataset.taskRow===focusedId)?.focus({preventScroll:true});
  $('empty').hidden=filtered.length>0;
  $('list-range').textContent=filtered.length?`${listPage*pageSize+1}–${listPage*pageSize+page.length} / ${filtered.length} 项`:'0 项';
  $('page-prev').disabled=listPage===0;$('page-next').disabled=(listPage+1)*pageSize>=filtered.length;
  document.querySelectorAll('[data-task-clock]').forEach(e=>{const t=tasks.find(t=>t.id===e.dataset.taskClock);if(t)e.textContent=taskElapsed(t);});
  updateDetailNav();
  if(selected&&$('detail-dialog').open){const task=tasks.find(t=>t.id===selected),metrics=$('detail-body').querySelector('.task-metrics');if(task&&metrics){if($('detail-body').dataset.rev!==String(task.rev)){const typed=$('detail-body').querySelector('.main-review-note')?.value,scroll=$('detail-dialog').scrollTop;showTask(task.id);if(typed!==undefined)$('detail-body').querySelector('.main-review-note').value=typed;$('detail-dialog').scrollTop=scroll;}else metrics.replaceWith(renderTaskMetrics(task));}}
  const issues=$('issues');issues.hidden=!state.issues.length;const list=issues.querySelector('ul');list.replaceChildren();for(const issue of state.issues)list.append(node('li','',issue.task+'：'+issue.message));
}
async function refresh(){if(loading||!projectId)return;loading=true;const requestedProject=projectId;try{const incoming=await api('/api/snapshot');if(requestedProject!==projectId)return;state=incoming;render();$('new-task').disabled=false;$('connection').textContent='● 实时连接 · '+new Date().toLocaleTimeString('zh-CN',{hour12:false});$('connection').classList.remove('offline');if(textJob&&$('text-dialog').open){const r=await api('/api/log/'+textJob);const pre=$('text-content');const end=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-40;pre.textContent=r.text||'等待日志…';if(end)pre.scrollTop=pre.scrollHeight;}}catch(e){$('connection').textContent='连接中断 · 正在重试';$('connection').classList.add('offline');notice(e.message);}finally{loading=false;if(requestedProject!==projectId)refresh();}}
function nextNumber(owner){const prefix={cursor:'CR',claude:'C',codex:'CX',deepseek:'D',lmstudio:'LM'}[owner]||'T';let i=1;while(state.tasks.some(t=>t.id===(owner||'pool')+':'+prefix+i))i++;return prefix+i;}
function configureAssignment(){const f=$('create-form'),owner=f.elements.owner.value,namespace=owner||'pool',id=f.elements.id.value;
  f.elements.dispatch.disabled=!owner;if(!owner)f.elements.dispatch.checked=false;
  $('assignment-hint').textContent=owner?'定向任务仅由所选成员领取，文件范围保持独立。':'发布后进入公共任务池，符合范围的成员都可领取；首个成功领取者获得任务。';
  f.elements.write_paths.value=namespace+'-works/'+(owner==='lmstudio'?'docs/':'src/')+id.toLowerCase()+'.'+(owner==='lmstudio'?'md':'dg');
}
function showCreate(){if(!projectId){notice('请先新增项目');return;}const f=$('create-form');f.reset();f.elements.id.value=nextNumber('');configureAssignment();$('create-error').textContent='';$('create-dialog').showModal();}

// ---- Task drawer ---------------------------------------------------------
function updateDetailNav(){
  const at=visibleIds.indexOf(selected);
  $('detail-prev').disabled=at<=0;$('detail-next').disabled=at<0||at>=visibleIds.length-1;
  for(const row of $('task-rows').children)row.classList.toggle('current',row.dataset.taskRow===selected);
}
function stepTask(offset){const at=visibleIds.indexOf(selected);const id=visibleIds[at+offset];if(at>=0&&id)showTask(id);}
function closeDetail(){if($('detail-dialog').open)$('detail-dialog').close();}
async function showTask(id){
  selected=id;const t=state.tasks.find(t=>t.id===id);if(!t)return;
  const detailProject=projectId;
  $('detail-id').textContent=t.id+' · '+(t.id.startsWith('pool:')?'公共任务':ownerName(t));$('detail-title').textContent=t.title;
  const body=$('detail-body');body.replaceChildren();body.dataset.rev=String(t.rev);
  const meta=node('div','detail-meta');meta.append(badge(t.status),node('span','muted','版本 '+t.rev+(t.historical?' · 历史独立验收':'')),node('span','muted','更新于 '+ago(t.updated_at)));
  if(t.claimed_by)meta.append(node('span','claimant','领取标识 '+t.claimed_by));
  const copy=button('复制编号',async()=>{await navigator.clipboard.writeText(t.id);copy.textContent='已复制';setTimeout(()=>{copy.textContent='复制编号';},1200);});copy.classList.add('small');meta.append(copy);
  body.append(meta,renderTaskMetrics(t),node('p','hint','经过时长包含暂停；提交后停止计时。验收、集成另行记录，历史缺失时间保持未知。'));
  const errorBox=node('p','');errorBox.id='detail-error';errorBox.setAttribute('role','alert');body.append(errorBox);
  const active=state.jobs.some(j=>j.task_id===id&&['queued','running'].includes(j.status));
  const note=node('textarea','review-note main-review-note');note.placeholder='返修请写清具体问题；验收与集成请记录真实审查依据。';note.setAttribute('aria-label','审查或返修说明');note.value=t.review_note||'';
  async function change(action,options){await actionRequest('/api/action',{task:t.id,rev:t.rev,action,note:note.value,options});}
  async function queue(kind,provider){await actionRequest('/api/queue',{task:t.id,rev:t.rev,kind,provider});}
  async function actionRequest(path,data){
    const typed=note.value;let message='';try{await action(path,data);}catch(e){message=e.message;}
    if(projectId!==detailProject||selected!==id||!$('detail-dialog').open)return;
    await showTask(t.id);$('detail-body').querySelector('.main-review-note').value=typed;$('detail-error').textContent=message;
  }
  const controls=node('div','actions task-actions');
  if(['todo','rework'].includes(t.status)){
    const claimant=node('select');claimant.setAttribute('aria-label','选择领取成员');
    if(!t.owner){for(const key of ['cursor','claude','codex','deepseek','lmstudio']){const op=node('option','',names[key]);op.value=key;claimant.append(op);}controls.append(claimant);}
    const claim=button(t.owner?'领取任务':'领取公共任务',()=>change('claim',{owner:t.owner||claimant.value}),active||Boolean(t.pause_requested_at));claim.classList.add('primary');controls.append(claim);
    const p=state.providers[t.owner]||{};
    if(t.owner)controls.append(button('排队执行 CLI',()=>queue('implement'),active||!p.available||!(p.modes||[]).includes('implement')));
  }
  if(t.owner&&['todo','in_progress','rework'].includes(t.status)){const submit=button('提交执行结果',()=>change('submit'),active||Boolean(t.pause_requested_at));if(t.status==='in_progress')submit.classList.add('primary');controls.append(submit);}
  if(t.status==='paused'&&t.pause_control==='confirmed')controls.append(button((t.assignment_owner??(t.id.startsWith('pool:')?null:t.id.split(':')[0]))?'释放任务':'释放回公共任务池',()=>change('release'),active));
  if(t.status==='submitted'){
    const verify=button('运行定向复验',()=>queue('verify'),active||!t.checks.length);verify.classList.add('primary');controls.append(verify);
    const reviewer=node('select');reviewer.setAttribute('aria-label','审查助手');
    for(const key of ['codex','claude','cursor']){const op=node('option','',names[key]);op.value=key;op.disabled=!state.providers[key]?.available;reviewer.append(op);}
    reviewer.value=t.owner==='codex'?'claude':'codex';controls.append(reviewer,button('只读审查',()=>queue('review',reviewer.value),active||!state.providers[reviewer.value]?.available),button('验收通过',()=>change('accept'),active||!t.verification?.passed),button('要求返修',()=>change('rework'),active));
  }
  if(t.status==='accepted')controls.append(button('确认已集成',()=>change('integrate'),active||!t.verification?.passed),button('要求返修',()=>change('rework'),active));
  if(!['accepted','integrated'].includes(t.status))controls.append(button(t.status==='paused'?(t.resume_status==='rework'?'恢复为待返修':'恢复任务'):active?'停止执行并暂停':'请求暂停',()=>change(t.status==='paused'?'resume':'pause'),Boolean(t.pause_requested_at)));
  if(controls.children.length)body.append(controls);
  const job=activeJob(id);
  if(job){const running=node('div','detail-job');running.append(node('span','',(jobNames[job.kind]||job.kind)+' · '+jobStates[job.status]+' · '+(names[job.provider]||job.provider)),button('查看日志',()=>showLog(job.id)));body.append(running);}
  if(t.verification)body.append(node('p','progress-position '+(t.verification.passed?'passed':'failed'),t.verification.summary));
  if(t.candidate)body.append(node('p','progress-position','交付位于隔离工作副本，尚未自动覆盖源码。'));
  if(t.pause_requested_at){
    const stopping=node('section','handoff-panel');
    stopping.append(node('strong','',t.pause_control==='managed'?'正在请求停止执行器':'等待外部执行者停止确认'));
    stopping.append(node('p','',t.pause_control==='managed'?'正在取消协调器启动的作业。确认进程退出后才能转派；恢复任务需重新执行，不是恢复原进程。':'此控制台不能停止 Cursor、MCP 客户端或手动执行的进程。请原领取者停止后确认，或先在外部停止，再在此明确确认。确认前不可转派。'));
    if(t.pause_control==='external'){
      const label=node('label','stop-confirm-label'),check=node('input');check.type='checkbox';label.append(check,document.createTextNode('我已在外部停止原执行者，不会继续写入任务文件'));
      const evidence=node('input','handoff-note');evidence.placeholder='停止依据，例如已在 Cursor 终止当前执行';evidence.setAttribute('aria-label','外部停止确认依据');
      const confirm=node('button','button','确认已停止');confirm.type='button';confirm.disabled=true;
      // Keep this a separate conscious confirmation from requesting pause or transferring.
      confirm.addEventListener('click',async()=>{if(confirm.disabled||!check.checked||!evidence.value.trim())return;confirm.disabled=true;await actionRequest('/api/action',{task:t.id,rev:t.rev,action:'confirm_pause',note:evidence.value,options:{stopped_confirmed:true}});});
      const enable=()=>confirm.disabled=!(check.checked&&evidence.value.trim());check.addEventListener('change',enable);evidence.addEventListener('input',enable);
      stopping.append(label,evidence,confirm);
    }
    body.append(stopping);
  }
  const description=node('section','task-description'),text=t.description||'暂无补充说明',long=text.length>480||text.split('\n').length>10;
  const paragraph=node('p',long&&expandedDescription!==t.id?'clamped':'',text);description.append(node('h3','','任务说明'),paragraph);
  if(long){const toggle=button(expandedDescription===t.id?'收起':'展开全文',()=>{expandedDescription=expandedDescription===t.id?null:t.id;paragraph.className=expandedDescription===t.id?'':'clamped';toggle.textContent=expandedDescription===t.id?'收起':'展开全文';});toggle.className='link';description.append(toggle);}
  body.append(description);
  if(t.depends_on.length){body.append(node('h3','','前置任务'));const deps=node('div','actions deps');for(const id of t.depends_on){const dep=state.tasks.find(x=>x.id===id);const b=button(dep?(dep.number+' · '+(state.labels[dep.status]||dep.status)):id+' · 依赖不存在',()=>showTask(id),!dep);b.title=dep?.title||id;if(dep)b.classList.add(DONE.includes(dep.status)?'dep-ready':'dep-waiting');deps.append(b);}body.append(deps);}
  if(['todo','rework','paused'].includes(t.status)&&!t.pause_requested_at){
    const transfer=node('details','detail-section transfer-section');transfer.append(node('summary','',t.status==='paused'?'暂停后转派':'指派 / 更换负责人'));
    transfer.append(node('p','hint','保留任务编号、授权路径、交付与历史。新成员须重新领取；旧领取令牌立即失效。'));
    const target=node('select');target.setAttribute('aria-label','转派给');
    for(const key of ['', 'cursor','claude','codex','deepseek','lmstudio']){const option=node('option','',key?names[key]:'不指定 · 公共领取');option.value=key;target.append(option);}target.value=t.owner||'';
    const handoff=node('textarea','review-note handoff-note');handoff.setAttribute('aria-label','转派交接说明');handoff.placeholder='交接进度、已完成内容、剩余工作和文件位置';
    const assign=button('确认指派',async()=>{if(!handoff.value.trim()){handoff.focus();return;}await actionRequest('/api/action',{task:t.id,rev:t.rev,action:'reassign',note:handoff.value,options:{owner:target.value||null}});},active);
    transfer.append(target,handoff,assign);body.append(transfer);
  }
  const scope=node('details','detail-section');scope.append(node('summary','','文件范围与定向测试 · '+t.write_paths.length+' 个路径 · '+t.checks.length+' 项测试'));
  const docs=node('div','actions');docs.append(button('查看任务书',()=>showDocument(t,'task')),button('查看交付',()=>showDocument(t,'delivery')));
  scope.append(docs,node('h3','','允许修改的文件'),node('div','path-list',t.write_paths.join('\n')),node('h3','','定向测试'),node('div','path-list',t.checks.join('\n')||'尚未配置定向测试'));body.append(scope);
  const review=node('details','detail-section');review.open=['submitted','rework','accepted'].includes(t.status);review.append(node('summary','','审查与返修说明'),note);body.append(review);
  const timing=node('details','detail-section');timing.append(node('summary','','每轮耗时与完整时间线'));renderTiming(timing,t);body.append(timing);
  if(!['accepted','integrated'].includes(t.status)){
    const advanced=node('details','detail-section');advanced.append(node('summary','','自动化选项'+(t.auto_dispatch||t.auto_verify?' · 已开启':'')));
    const options=node('div','toggle-row'),a=node('label'),b=node('label'),auto=node('input'),verify=node('input');auto.type=verify.type='checkbox';auto.checked=t.auto_dispatch;verify.checked=t.auto_verify;auto.disabled=active||!t.owner;verify.disabled=active;
    a.append(auto,document.createTextNode(' 自动派单'));b.append(verify,document.createTextNode(' 新交付自动复验'));options.append(a,b);
    for(const box of [auto,verify])box.addEventListener('change',()=>change('automation',{auto_dispatch:auto.checked,auto_verify:verify.checked}).catch(()=>{}));
    advanced.append(options,node('p','hint','需另行开启工作区自动化。公共任务不会自动指定负责人；测试通过不会自动验收。'));body.append(advanced);
  }
  updateDetailNav();
  if(!$('detail-dialog').open){$('detail-dialog').show();document.body.dataset.drawer='open';$('close-detail').focus({preventScroll:true});}
}
async function showDocument(task,kind){textJob=null;const request=++documentRequest,project=projectId;try{const r=await api('/api/document?task='+encodeURIComponent(task.id)+'&kind='+kind);if(request!==documentRequest||project!==projectId)return;$('text-title').textContent=task.id+' · '+(kind==='task'?'任务书':'交付');$('text-content').textContent=r.text;if(!$('text-dialog').open)$('text-dialog').showModal();}catch(e){notice(e.message);}}
async function showLog(id){textJob=id;const request=++documentRequest,project=projectId;try{const r=await api('/api/log/'+id);if(request!==documentRequest||project!==projectId)return;$('text-title').textContent='执行日志 · '+id.slice(0,8);$('text-content').textContent=r.text||'等待日志…';if(!$('text-dialog').open)$('text-dialog').showModal();}catch(e){if(request===documentRequest)notice(e.message);}}

// ---- Bindings ------------------------------------------------------------
$('new-task').addEventListener('click',showCreate);for(const [id,dialog]of[['close-create','create-dialog'],['close-detail','detail-dialog'],['close-text','text-dialog']])$(id).addEventListener('click',()=>$(dialog).close());$('text-dialog').addEventListener('close',()=>{textJob=null;documentRequest++;});
$('detail-dialog').addEventListener('close',()=>{selected=null;document.body.dataset.drawer='';updateDetailNav();});
$('detail-prev').addEventListener('click',()=>stepTask(-1));$('detail-next').addEventListener('click',()=>stepTask(1));
document.querySelectorAll('[data-owner]').forEach(b=>b.addEventListener('click',()=>showTasks(undefined,ownerFilter===b.dataset.owner&&document.body.dataset.page==='tasks'?'':b.dataset.owner)));
document.querySelectorAll('[data-jump]').forEach(b=>b.addEventListener('click',()=>showTasks(b.dataset.jump,'')));
$('search').addEventListener('input',()=>{listPage=0;if(state)render();});
$('event-search').addEventListener('input',()=>{if(state)renderActivity();});
$('progress-reset').addEventListener('click',()=>{ownerFilter='';statusFilter='';listPage=0;$('search').value='';syncOwnerNav();if(state)render();});
$('roadmap-download').addEventListener('click',downloadRoadmap);
$('sync').addEventListener('click',()=>action('/api/sync',{}).catch(()=>{}));$('doctor').addEventListener('click',async()=>{const b=$('doctor');b.disabled=true;b.textContent='正在检测…';try{await action('/api/doctor',{});}catch{}finally{b.disabled=false;b.textContent='重新检测 CLI ↻';}});
$('automation').addEventListener('change',()=>action('/api/automation',{enabled:$('automation').checked}).catch(()=>{}));
$('owner-filter').addEventListener('change',e=>{ownerFilter=e.target.value;listPage=0;syncOwnerNav();if(state)render();});
$('sort-order').addEventListener('change',e=>{sortOrder=e.target.value;listPage=0;if(state)render();});
$('page-size').addEventListener('change',e=>{pageSize=Number(e.target.value)||20;listPage=0;if(state)render();});
document.querySelectorAll('[data-quick]').forEach(b=>b.addEventListener('click',()=>{statusFilter=b.dataset.quick;listPage=0;if(state)render();}));
document.querySelectorAll('[data-job-filter]').forEach(b=>b.addEventListener('click',()=>{jobFilter=b.dataset.jobFilter;if(state)renderRuntime();}));
for(const view of ['list','board'])$('view-'+view).addEventListener('click',()=>{document.body.dataset.view=view;for(const name of ['list','board'])$('view-'+name).setAttribute('aria-pressed',String(view===name));});
$('page-prev').addEventListener('click',()=>{listPage--;render();});$('page-next').addEventListener('click',()=>{listPage++;render();});
$('create-form').elements.owner.addEventListener('change',e=>{const f=$('create-form');f.elements.id.value=nextNumber(e.target.value);configureAssignment();});
$('create-form').addEventListener('submit',async e=>{
  e.preventDefault();const f=e.currentTarget,b=f.querySelector('[type=submit]');if(b.disabled)return;b.disabled=true;$('create-error').textContent='';
  try{
    const lines=name=>f.elements[name].value.split('\n').map(x=>x.trim()).filter(Boolean);
    const dispatch=f.elements.dispatch.checked,creationProject=projectId;
    const task=await api('/api/tasks',{id:f.elements.id.value.trim(),owner:f.elements.owner.value||null,title:f.elements.title.value.trim(),description:f.elements.description.value,write_paths:lines('write_paths'),checks:lines('checks'),depends_on:f.elements.depends_on.value.split(',').map(x=>x.trim()).filter(Boolean)});
    const reveal=projectId===creationProject&&$('create-dialog').open;
    $('create-dialog').close();
    if(dispatch&&projectId===creationProject){try{await api('/api/queue',{task:task.id,rev:task.rev,kind:'implement'});}catch(error){notice('任务已发布；排队未成功：'+error.message);}}
    await refresh();if(reveal&&projectId===creationProject)await showTask(task.id);
  }catch(error){$('create-error').textContent=error.message;await refresh();}finally{b.disabled=false;}
});
window.addEventListener('hashchange',()=>go(location.hash.slice(1),{push:false}));
document.addEventListener('keydown',e=>{
  const modal=['create-dialog','text-dialog','project-dialog'].some(id=>$(id).open),typing=/^(INPUT|TEXTAREA|SELECT)$/i.test(e.target?.tagName||'');
  if(e.key==='Escape'&&!modal&&$('detail-dialog').open){e.preventDefault();closeDetail();return;}
  if(e.key==='/'&&!modal&&!typing&&!e.ctrlKey&&!e.metaKey){e.preventDefault();go('tasks');$('search').focus();}
});
async function boot(){go(location.hash.slice(1),{push:false});try{const session=await api('/api/session');csrf=session.csrf;setProjects(session.projects);go(location.hash.slice(1),{push:false});await refresh();setInterval(()=>{if(!busy)refresh();},2000);}catch(e){notice(e.message);}}boot();

function setProjects(items,preferred){projectList=items;const existing=preferred||projectId||localStorage.getItem('coordination-project');projectId=items.some(p=>p.id===existing)?existing:(items[0]?.id||'');const select=$('project-select');select.replaceChildren();for(const p of items){const option=node('option','',p.name);option.value=p.id;select.append(option);}if(!items.length)select.append(node('option','','请新增项目'));select.value=projectId;const project=items.find(p=>p.id===projectId);$('project-location').textContent=project?project.works_root:'每个项目的任务、测试、交付和日志集中保存';$('project-location').title=project?.works_root||'';$('new-task').disabled=!projectId;localStorage.setItem('coordination-project',projectId);}
$('project-select').addEventListener('change',async e=>{if(busy){e.target.value=projectId;return;}projectId=e.target.value;state=null;clearProgress();clearRoadmap();for(const id of ['task-rows','jobs','events','attention-list','member-cards','overview-jobs','overview-events'])$(id).replaceChildren();$('new-task').disabled=true;ownerFilter='';statusFilter='';listPage=0;$('search').value='';for(const dialog of document.querySelectorAll('dialog'))dialog.close();syncOwnerNav();const activeProject=projectList.find(p=>p.id===projectId);$('project-location').textContent=activeProject?.works_root||'';$('project-location').title=activeProject?.works_root||'';localStorage.setItem('coordination-project',projectId);go(document.body.dataset.page,{push:false});await refresh();});
$('new-project').addEventListener('click',()=>{$('project-form').reset();$('project-error').textContent='';$('project-dialog').showModal();});
$('close-project').addEventListener('click',()=>$('project-dialog').close());
$('project-form').addEventListener('submit',async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('[type=submit]');b.disabled=true;try{const item=await api('/api/projects',{id:f.elements.id.value.trim(),name:f.elements.name.value.trim(),source_root:f.elements.source_root.value.trim()});setProjects(await api('/api/projects'),item.id);$('project-dialog').close();await refresh();}catch(error){$('project-error').textContent=error.message;}finally{b.disabled=false;}});
$('export-link').addEventListener('click',async e=>{e.preventDefault();const data=await api('/api/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download=projectId+'-tasks.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
