const statusLabels: Record<string,string> = {
  pending:'待主任审核',
  draft:'草案',
  submitted:'待管理员确认',
  approved:'管理员已确认',
  returned:'管理员退回',
  stale:'安排已变化，需重审',
};

export function departmentScheduleDraft(task:any){
  return {
    base_revision:task.plan_revision,
    base_fingerprint:task.base_fingerprint,
    teacher_ids:task.proposal?.teacher_ids||task.teacher_ids||[],
    reason:task.proposal?.reason||'',
  };
}

export function departmentScheduleStatusLabel(status:string){
  return statusLabels[status]||statusLabels.pending;
}

export function departmentScheduleEditable(task:any){
  return Boolean(task.can_edit_department_schedule) && task.plan_state!=='published' &&
    !['submitted','approved'].includes(task.department_schedule_status);
}

/** Directors may directly assign only courses that no latest submission claims. */
export function departmentDirectAssign(task:any){
  if (typeof task?.can_direct_assign === 'boolean') return task.can_direct_assign;
  if (typeof task?.has_applications === 'boolean') return !task.has_applications;
  return !(task?.applicants||[]).some((applicant:any)=>applicant.selected!==false);
}

const weekdays=['','周一','周二','周三','周四','周五','周六','周日'];
export function formatTeachingSlots(slots:any[]=[]){
  return slots.map(slot=>`${weekdays[slot.day]||`周${slot.day}`}第${slot.start}-${slot.start+slot.count-1}节${slot.phase==='tail'?'（尾周）':''}`).join('；')||'尚未安排周内节次';
}
