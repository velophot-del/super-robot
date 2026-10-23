import test from 'node:test';
import assert from 'node:assert/strict';
test('stage cells distinguish taught periods, reserved remainder, and free time',async()=>{
  const {stageCell}=await import('../src/lib/stageGrid.ts');
  const tasks=[{id:1,start_week:1,end_week:4,tail_weeks:0,slots:[{day:1,start:1,count:4,phase:'normal'}]}];
  assert.equal(stageCell(tasks,1,1,4).state,'teaching');
  assert.equal(stageCell(tasks,1,1,5).state,'reserved');
  assert.equal(stageCell(tasks,1,2,5).state,'free');
  assert.equal(stageCell(tasks,5,1,1).state,'free');
});

test('compact stage rows reserve a fixed height per overlapping course',async()=>{
  const {stageRowMetrics}=await import('../src/lib/adminStageGrid.ts');
  const lanes=[{task:{id:1},lane:0},{task:{id:2},lane:1}];
  const metrics=stageRowMetrics(lanes);
  assert.equal(metrics.rowHeight,178);
  assert.equal(metrics.laneStep,90);
});

test('clicking a placed course title invokes the task editor callback',async()=>{
  const {stageTaskEditAction}=await import('../src/lib/adminStageGrid.ts');
  const task={id:17,name:'图形创意思维'};
  let edited;
  stageTaskEditAction(task,value=>{edited=value;})();
  assert.equal(edited,task);
});

test('stage cards show an assigned room or an unassigned label',async()=>{
  const {stageRoomLabel}=await import('../src/lib/adminStageGrid.ts');
  assert.equal(stageRoomLabel('设计楼 302'), '设计楼 302');
  assert.equal(stageRoomLabel(null), '未分配');
  assert.equal(stageRoomLabel('  '), '未分配');
});

test('stage filters use curriculum task scope and fall back to class records',async()=>{
  const {matchesStageScope,normalizeCohort,stageClassScope}=await import('../src/lib/adminStageGrid.ts');
  const classes=[{name:'视传2601',grade:'2026级',department:'视觉传达设计'},
    {name:'视传2602',grade:'2026',department:'视觉传达设计'}];
  const tasks=[{group:'视传2601',cohort:'2026',major:'视传设计'}];
  assert.deepEqual(stageClassScope('视传2601',classes,tasks),{cohort:'2026',major:'视传设计'});
  assert.deepEqual(stageClassScope('视传2602',classes,[]),{cohort:'2026',major:'视觉传达设计'});
  assert.equal(normalizeCohort('21级'),'21');
  assert.equal(matchesStageScope({cohort:'2026',major:'视传设计'},'2026','视传设计'),true);
  assert.equal(matchesStageScope({cohort:'2026',major:'视传设计'},'2025','视传设计'),false);
});
