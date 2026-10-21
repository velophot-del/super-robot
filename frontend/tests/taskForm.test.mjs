import test from 'node:test';
import assert from 'node:assert/strict';

test('task settings send only teacher count, student limit and revision',async()=>{
  const {taskLimitsPayload}=await import('../src/lib/taskForm.ts');
  const result=taskLimitsPayload({teacher_count:2,max_students:45,name:'Tampered',start_week:9,end_week:19,tail_weeks:2,student_count:99,room_id:null},3);
  assert.deepEqual(result,{revision:3,teacher_count:2,max_students:45});
});

test('read-only course info uses imported metadata rather than changed task fields',async()=>{
  const {taskCourseInfo}=await import('../src/lib/taskForm.ts');
  const result=taskCourseInfo({name:'Changed',code:'Changed',credits:9,required_hours:99,group:'G',source:{major:'Design',course_metadata:{name:'Imported',code:'D1',credits:2,required_hours:32,category:'专业必修'}}});
  assert.equal(result.name,'Imported');assert.equal(result.code,'D1');
  assert.equal(result.credits,2);assert.equal(result.required_hours,32);
  assert.equal(result.group,'G');assert.equal(result.department,'Design');
});
