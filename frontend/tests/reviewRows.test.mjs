import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewRows} from '../src/lib/reviewRows.ts';
import {openSelectionPlans} from '../src/lib/teacherWorkbench.ts';
import {departmentDirectAssign,departmentScheduleDraft,departmentScheduleStatusLabel,departmentScheduleEditable,formatTeachingSlots} from '../src/lib/departmentSchedule.ts';

test('review aggregates canonical classes across plans and historical cohort formats',()=>{
  const base={start_week:1,end_week:2,group:'Class A',major:'Design'};
  const rows=reviewRows([{...base,id:1,cohort:'2026'},{...base,id:2,cohort:'2026届'},{...base,id:3,cohort:'26级'}],{});
  assert.equal(rows.length,1);assert.equal(rows[0][1].tasks.length,3);
  const canonical=reviewRows([{...base,id:1,class_id:4,cohort:'2026'},{...base,id:2,class_id:4,cohort:'2026级',major:'Old name'}],{});
  assert.equal(canonical.length,1);
});
test('returned applications are editable after matching without opening all teachers',()=>{
  const expired={state:'matched',deadline:'2020-01-01'};
  assert.equal(openSelectionPlans([{...expired,id:1,can_resubmit:true},{...expired,id:2}]).length,1);
});
test('department schedule draft contains only teacher proposal and rationale',()=>{
  const task={plan_revision:5,base_fingerprint:'a'.repeat(64),start_week:1,end_week:4,room_id:31,teacher_ids:[7],slots:[{day:1,start:1,count:2}],proposal:{start_week:3,end_week:5,room_id:null,teacher_ids:[8],slots:[]}};
  assert.deepEqual(departmentScheduleDraft(task),{base_revision:5,base_fingerprint:'a'.repeat(64),teacher_ids:[8],reason:''});
});
test('course schedule status and editability expose submitted lock and pending admin state',()=>{
  assert.equal(departmentScheduleStatusLabel('submitted'),'待管理员确认');
  assert.equal(departmentScheduleEditable({can_edit_department_schedule:true,department_schedule_status:'draft',plan_state:'open'}),true);
  assert.equal(departmentScheduleEditable({can_edit_department_schedule:true,department_schedule_status:'submitted',plan_state:'open'}),false);
  assert.equal(departmentScheduleEditable({can_edit_department_schedule:false,department_schedule_status:'draft',plan_state:'open'}),false);
});
test('director direct assignment is limited to globally unclaimed courses',()=>{
  assert.equal(departmentDirectAssign({applicants:[]}),true);
  assert.equal(departmentDirectAssign({applicants:[{selected:false}]}),true);
  assert.equal(departmentDirectAssign({applicants:[{selected:true}]}),false);
  assert.equal(departmentDirectAssign({has_applications:false,applicants:[{selected:true}]}),true);
  assert.equal(departmentDirectAssign({has_applications:true,applicants:[]}),false);
  assert.equal(departmentDirectAssign({can_direct_assign:false,has_applications:false}),false);
});
test('teaching period slots are compactly summarized for schedule cards',()=>{
  assert.equal(formatTeachingSlots([{day:2,start:3,count:4,phase:'normal'},{day:5,start:1,count:2,phase:'tail'}]),'周二第3-6节；周五第1-2节（尾周）');
});
