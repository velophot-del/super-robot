import { normalizeCohort } from './adminStageGrid.ts';

export function reviewRows(tasks:any[], plan:any){
  const groups=new Map<string,{major:string;cohort:string;group:string;tasks:any[]}>();
  const seen=new Set<number>();
  for(const task of tasks){
    if(!task.start_week||!task.end_week||seen.has(task.id))continue;
    seen.add(task.id);
    const major=String(task.major||task.department||task.source?.major||plan.major||'未注明专业').trim();
    let cohort=normalizeCohort(task.cohort||plan.cohort);
    if(/^\d{2}$/.test(cohort))cohort=`20${cohort}`;
    const group=String(task.class_name||task.group||'').trim();
    const key=task.class_id?`class:${task.class_id}`:`${major}|${cohort}|${group}`;
    if(!groups.has(key))groups.set(key,{major,cohort,group,tasks:[]});
    groups.get(key)!.tasks.push(task);
  }
  return [...groups.entries()].sort(([a],[b])=>a.localeCompare(b,'zh-CN'));
}
