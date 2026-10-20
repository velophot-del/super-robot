import test from 'node:test';
import assert from 'node:assert/strict';

test('stage selection grid merges identical week content but splits tail periods',async()=>{
  const {selectionSegments}=await import('../src/lib/selectionGrid.ts');
  const first={id:1,name:'A',start_week:1,end_week:4,tail_weeks:1};
  const second={id:2,name:'B',start_week:2,end_week:3};
  const rows=selectionSegments([first,second],6);
  assert.deepEqual(rows.map(s=>[s.start,s.span,s.tasks.map(t=>t.id)]),[[1,1,[1]],[2,2,[1,2]],[4,1,[1]],[5,1,[]],[6,1,[]]]);
  assert.equal(rows[2].tail,true);
  assert.equal(rows.reduce((sum,s)=>sum+s.span,0),6);
});

test('academic filters distinguish school year, semester, and cross-major plans',async()=>{
  const {academicYear,filterSelectionPlans}=await import('../src/lib/selectionGrid.ts');
  assert.equal(academicYear('2027-02-01'),'2026—2027');
  assert.equal(academicYear('2027-09-06'),'2027—2028');
  const plans=[{id:1,start_date:'2026-09-07',semester:1,major:'Design'},{id:2,start_date:'2027-02-01',semester:2,major:'Art'},{id:3,start_date:'2027-09-06',semester:3,major:'Design'}];
  assert.deepEqual(filterSelectionPlans(plans,'2026—2027','all','all').map(p=>p.id),[1,2]);
  assert.deepEqual(filterSelectionPlans(plans,'2026—2027','2','all').map(p=>p.id),[2]);
  assert.deepEqual(filterSelectionPlans(plans,'2026—2027','all','Design').map(p=>p.id),[1]);
});

test('administrator week positions cover twenty columns and overlaps use separate lanes',async()=>{
  const {dropWeek,stageLanes}=await import('../src/lib/adminStageGrid.ts');
  assert.equal(dropWeek(150,100,1000),2);
  assert.equal(dropWeek(1100,100,1000),20);
  assert.equal(dropWeek(99,100,1000),1);
  const bars=stageLanes([{id:1,start_week:1,end_week:5},{id:2,start_week:3,end_week:6},{id:3,start_week:6,end_week:8}]);
  assert.deepEqual(bars.map(b=>[b.task.id,b.lane]),[[1,0],[2,1],[3,0]]);
});

 test('only week twenty is reserved for exams',async()=>{
 const {selectionSegments}=await import('../src/lib/selectionGrid.ts');
 assert.deepEqual(selectionSegments([],20).map(s=>[s.start,s.span,s.exam]),[[1,19,false],[20,1,true]]);
 });
