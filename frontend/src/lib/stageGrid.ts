type StageTask = {id:number; start_week:number; end_week:number; tail_weeks?:number; slots:{day:number;start:number;count:number;phase?:string}[]};
export function stageCell<T extends StageTask>(tasks:T[],week:number,day:number,period:number):{state:'free'|'reserved'|'teaching';task?:T}{
  for(const task of tasks){
    if(!task.start_week||week<task.start_week||week>task.end_week)continue;
    const phase=task.tail_weeks&&week>task.end_week-task.tail_weeks?'tail':'normal';
    const slot=task.slots.find(s=>s.day===day&&(s.phase||'normal')===phase);
    if(slot)return {state:period>=slot.start&&period<slot.start+slot.count?'teaching':'reserved',task};
  }
  return {state:'free'};
}
