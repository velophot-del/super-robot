export type SelectionTask = {id:number;start_week:number;end_week:number;tail_weeks?:number};
export type SelectionPlan = {id:number;start_date:string;semester?:number;major?:string;academic_year?:string;academic_term?:number};

export function academicYear(start:string):string{
  const year=Number(start.slice(0,4)),first=Number(start.slice(5,7))>=8?year:year-1;
  return `${first}—${first+1}`;
}

export function filterSelectionPlans<T extends SelectionPlan>(plans:T[],year:string,term:string,major:string):T[]{
  return plans.filter(p=>(p.academic_year||academicYear(p.start_date))===year&&
    (term==='all'||String(p.academic_term||((p.semester||2)%2?1:2))===term)&&
    (major==='all'||p.major===major));
}

export function selectionSegments<T extends SelectionTask>(tasks:T[],weeks:number){
  const result:{start:number;span:number;tasks:T[];tail:boolean;exam:boolean;key:string}[]=[];
  for(let week=1;week<=weeks;week++){
    const active=tasks.filter(t=>t.start_week&&week>=t.start_week&&week<=t.end_week).sort((a,b)=>a.id-b.id);
    const tail=(t:T)=>Boolean(t.tail_weeks&&week>t.end_week-t.tail_weeks);
    const exam=!active.length&&week>weeks-1;
    const key=active.map(t=>`${t.id}:${tail(t)?'tail':'normal'}`).join(',')+(exam?':exam':'');
    const previous=result.at(-1);
    if(previous?.key===key)previous.span++;
    else result.push({start:week,span:1,tasks:active,tail:active.some(tail),exam,key});
  }
  return result;
}

export function weekDates(start:string,week:number):string{
  const day=new Date(`${start}T00:00:00Z`);day.setUTCDate(day.getUTCDate()+(week-1)*7);
  const label=(d:Date)=>`${d.getUTCMonth()+1}.${d.getUTCDate()}`;
  const end=new Date(day);end.setUTCDate(end.getUTCDate()+6);
  return `${label(day)}—${label(end)}`;
}

const days=['周一','周二','周三','周四','周五','周六','周日'];
export function selectionSlots(task:{end_week:number;tail_weeks?:number;slots?:{day:number;start:number;count:number;phase?:string}[]},week?:number):string{
  const tail=week!==undefined&&task.tail_weeks&&week>task.end_week-task.tail_weeks;
  const slots=(task.slots||[]).filter(s=>week===undefined||(s.phase||'normal')===(tail?'tail':'normal'));
  return slots.map(s=>`${s.phase==='tail'?'尾段 ':''}${days[s.day-1]} ${s.start}—${s.start+s.count-1}节`).join('；');
}

