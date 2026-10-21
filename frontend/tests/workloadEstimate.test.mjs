import test from 'node:test';
import assert from 'node:assert/strict';

test('workload kind identifies shared teaching and graduation supervision',async()=>{
  const {workloadKind}=await import('../src/lib/workloadEstimate.ts');
  assert.equal(workloadKind({name:'普通课程',teacher_count:1}),'ordinary');
  assert.equal(workloadKind({name:'多人课程',teacher_count:2}),'shared');
  assert.equal(workloadKind({name:'毕业设计（创作）'}),'design');
  assert.equal(workloadKind({name:'毕业论文'}),'thesis');
  assert.equal(workloadKind({name:'毕业设计（论文）'}),'ambiguous');
});

test('estimated workload uses the 25-person base, real tail hours, week allocation and supervision rates',async()=>{
  const {estimateWorkload}=await import('../src/lib/workloadEstimate.ts');
  const tasks=[
    {id:1,name:'普通课程',required_hours:32,student_count:30,start_week:1,end_week:4,slots:[{day:1,start:1,count:8,phase:'normal'}]},
    {id:2,name:'尾周课程',required_hours:10,student_count:25,start_week:1,end_week:3,tail_weeks:1,slots:[{day:1,start:1,count:4,phase:'normal'},{day:2,start:1,count:2,phase:'tail'}]},
    {id:3,name:'多人课程',required_hours:8,teacher_count:2,student_count:25,start_week:1,end_week:2,slots:[{day:1,start:1,count:4,phase:'normal'}]},
    {id:4,name:'毕业设计',student_count:30},
    {id:5,name:'毕业论文',student_count:30},
  ];
  const result=estimateWorkload(tasks,[1,2,3,4,5],{3:{weeks:1},4:{guidance_students:2},5:{guidance_students:3}});
  assert.equal(result.total,94);                    // 32 + 10 + 4 + 24 + 24（预估统一按25人基数1）
  assert.equal(result.pending,0);
  assert.equal(result.rows[0].hours,32);
  assert.equal(result.rows[1].hours,10);
  assert.equal(result.rows[2].hours,4);
  assert.equal(estimateWorkload(tasks,[3],{}).pending,1);
});

test('only shared and graduation courses need teacher parameters',async()=>{
  const {workloadParameterRows}=await import('../src/lib/workloadEstimate.ts');
  const tasks=[{id:1,name:'普通课程',teacher_count:1},{id:2,name:'多人课程',teacher_count:2},
    {id:3,name:'毕业设计'},{id:4,name:'未选毕业论文'}];
  const rows=workloadParameterRows(tasks,[1,2,3]);
  assert.deepEqual(rows.map(row=>[row.id,row.kind]),[[2,'shared'],[3,'design']]);
});
