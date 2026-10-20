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
