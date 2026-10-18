const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../dongos_coordination/web/app.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('const progressStages ='),source.indexOf('\nasync function api'))+'\nglobalThis.build=buildProgress;',context);
const build=(tasks,all=tasks,jobs=[])=>JSON.parse(JSON.stringify(context.build(tasks,all,jobs)));
const task=(id,status,deps=[])=>({id,number:id.split(':')[1],owner:id.split(':')[0],title:id,status,depends_on:deps});

test('real states are partitioned once; submission, rework and pause never count as acceptance',()=>{
  const statuses=['todo','in_progress','submitted','rework','accepted','integrated','paused'];
  const tasks=statuses.map((s,i)=>task('cursor:CR'+i,s));
  const model=build(tasks);
  assert.equal(model.total,7);assert.equal(model.accepted,2);assert.equal(model.integrated,1);
  assert.equal(model.lanes.reduce((n,l)=>n+l.tasks.length,0),7);
  for(const lane of model.lanes)assert.equal(lane.tasks.length,1);
  assert.equal(model.blocked,0);
});
test('dependencies use all project tasks even when only one owner or search result is visible',()=>{
  const prerequisite=task('cursor:CR4','submitted'),next=task('cursor:CR5','todo',['cursor:CR4']);
  let model=build([next],[prerequisite,next]);
  assert.equal(model.blocked,1);assert.equal(model.lanes[0].tasks[0].waiting[0].id,'cursor:CR4');
  for(const status of ['accepted','integrated']){
    prerequisite.status=status;model=build([next],[prerequisite,next]);
    assert.equal(model.blocked,0);assert.equal(model.lanes[0].tasks[0].dependencies[0].ready,true);
  }
  model=build([next],[next]);assert.equal(model.blocked,1);
  assert.equal(model.lanes[0].tasks[0].waiting[0].ready,false);
});
test('fresh snapshots move a task from submitted to rework without inventing a completion percentage',()=>{
  const item=task('deepseek:D16','submitted');
  assert.equal(build([item]).lanes.find(l=>l.status==='submitted').tasks.length,1);
  item.status='rework';const model=build([item]);
  assert.equal(model.lanes.find(l=>l.status==='submitted').tasks.length,0);
  assert.equal(model.lanes.find(l=>l.status==='rework').tasks.length,1);assert.equal(model.accepted,0);
  item.status='accepted';assert.equal(build([item]).accepted,1);assert.equal(build([item]).integrated,0);
});
test('only an actual active job on this task is displayed; old failures cannot mask a new verification',()=>{
  const t=task('deepseek:D16','submitted');
  const jobs=[{id:'old',task_id:t.id,kind:'verify',status:'failed',created:'2026-10-18T00:00:00Z'},
    {id:'other',task_id:'cursor:CR4',kind:'implement',status:'running',created:'2026-10-18T01:00:00Z'},
    {id:'new',task_id:t.id,kind:'verify',status:'running',created:'2026-10-18T02:00:00Z'}];
  assert.equal(build([t],[t],jobs).lanes.find(l=>l.status==='submitted').tasks[0].active.id,'new');
  jobs[2].status='completed';assert.equal(build([t],[t],jobs).lanes.find(l=>l.status==='submitted').tasks[0].active,undefined);
});
test('empty filters, unknown states and task ordering preserve every item and leave snapshots untouched',()=>{
  const tasks=[task('cursor:CR10','todo'),task('cursor:CR2','todo'),task('cursor:CR1','future')];
  const before=JSON.stringify(tasks);const model=build(tasks);
  assert.deepEqual(model.lanes[0].tasks.map(i=>i.task.id),['cursor:CR2','cursor:CR10']);
  assert.equal(model.lanes.find(l=>l.status==='unknown').tasks[0].task.id,'cursor:CR1');
  assert.equal(JSON.stringify(tasks),before);
  assert.equal(build([],tasks).total,0);assert.equal(build([],tasks).accepted,0);
});
