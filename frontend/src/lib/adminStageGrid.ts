export function stageLanes<T extends {id:number;start_week:number;end_week:number}>(tasks:T[]):{task:T;lane:number}[]{
  const ends:number[]=[];
  return [...tasks].sort((a,b)=>a.start_week-b.start_week||a.id-b.id).map(task=>{
    let lane=ends.findIndex(end=>end<task.start_week);if(lane<0)lane=ends.length;
    ends[lane]=task.end_week;return {task,lane};
  });
}
export function dropWeek(clientX:number,left:number,width:number,weeks=20):number{
  return Math.max(1,Math.min(weeks,Math.floor((clientX-left)/width*weeks)+1));
}

export function normalizeCohort(value:unknown):string{
  const text=String(value??'').trim().replace(/(级|届)$/,'');
  const year=text.match(/^(\d{4})/)?.[1];
  return year||text;
}

export function gradeLabel(value:unknown):string{
  const grade=normalizeCohort(value);
  return grade?`${grade}级`:'';
}

/** 当前在校的四个年级，按学年起始年（8 月起算新学年）倒序。 */
export function currentGradeCohorts(now:Date=new Date()):string[]{
  const start=now.getMonth()>=7?now.getFullYear():now.getFullYear()-1;
  return Array.from({length:4},(_,offset)=>String(start-offset));
}

/** 年级页签匹配；未填年级的记录在每个页签保留，避免静默漏课。 */
export function matchesGrade(value:unknown,cohort:string):boolean{
  const grade=normalizeCohort(value);
  return !grade||grade===normalizeCohort(cohort);
}

export function stageRowMetrics(lanes:{task:{id:number};lane:number}[]){
  const cardHeight=84,laneStep=90;
  const rowHeight=Math.max(90,...lanes.map(({lane})=>lane*laneStep+cardHeight+4));
  return {laneStep,rowHeight};
}

export function stageTaskEditAction<T>(task:T,onEdit:(task:T)=>void):()=>void{
  return ()=>onEdit(task);
}

export function stageRoomLabel(value:unknown):string{
  return String(value??'').trim()||'未分配';
}

export function stageClassScope(group:string,classes:{name:string;grade?:string;department?:string}[],tasks:{group:string;cohort?:string;major?:string;department?:string}[]):{cohort:string;major:string}{
  const task=tasks.find(row=>row.group===group&&(row.cohort||row.major||row.department));
  const classRow=classes.find(row=>row.name===group);
  return {
    cohort:normalizeCohort(task?.cohort||classRow?.grade),
    major:String(task?.major||task?.department||classRow?.department||'').trim(),
  };
}

export function matchesStageScope(scope:{cohort?:string;major?:string},cohort:string,major:string):boolean{
  return (cohort==='__all__'||normalizeCohort(scope.cohort)===cohort)
    &&(major==='__all__'||String(scope.major||'').trim()===major);
}
