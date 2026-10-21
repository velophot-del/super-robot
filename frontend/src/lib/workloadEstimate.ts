export type EstimateInput={revision?:number;weekly_hours?:number|null;weeks?:number|null;guidance_students?:number|null;guidance_kind?:'design'|'thesis'|null};
export type WorkloadKind='ordinary'|'shared'|'design'|'thesis'|'ambiguous';

export function workloadKind(task:any):WorkloadKind{
  const name=String(task?.source?.course_metadata?.name??task?.name??'').replace(/\s/g,'');
  if(name.includes('毕业')&&name.includes('设计')&&name.includes('论文'))return 'ambiguous';
  if(name.includes('毕业设计'))return 'design';
  if(name.includes('毕业论文'))return 'thesis';
  return Number(task?.teacher_count)>1?'shared':'ordinary';
}

export function workloadParameterRows(tasks:any[],selected:number[]){
  return [...new Set(selected)].map(id=>{
    const task=tasks.find(item=>item.id===id);
    return {id,task,kind:workloadKind(task)};
  }).filter(row=>row.task&&row.kind!=='ordinary');
}

export function actualHours(task:any){
  const start=Number(task?.start_week||0),end=Number(task?.end_week||0);
  if(task?.slots?.length&&start>0&&end>=start){
    let total=0;
    for(let week=start;week<=end;week++){
      const phase=task.tail_weeks&&week>end-task.tail_weeks?'tail':'normal';
      total+=(task.slots||[]).filter((slot:any)=>(slot.phase||'normal')===phase)
        .reduce((sum:number,slot:any)=>sum+Number(slot.count||0),0);
    }
    return total;
  }
  const meta=task?.source?.course_metadata||{};
  const tailWeeks=Number(task?.tail_weeks||0),tailHours=Number(meta.tail_hours),weekly=Number(meta.weekly_hours);
  if(start>0&&end>=start&&tailWeeks>0&&Number.isFinite(tailHours)&&Number.isFinite(weekly)){
    const span=end-start+1;
    return Math.max(0,span-tailWeeks)*weekly+tailWeeks*tailHours;
  }
  return Number(task?.required_hours||0);
}

export function estimateWorkload(tasks:any[],selected:number[],inputs:Record<number,EstimateInput>){
  const rows=[...new Set(selected)].map(id=>{
    const task=tasks.find(item=>item.id===id),input=inputs[id]||{},kind=workloadKind(task);
    let hours:number|null=null,formula='待补充';
    if(task){
      // 选课阶段统一按 25 人基数 1 预估，不使用班级实际人数系数。
      if(kind==='design'||kind==='thesis'||kind==='ambiguous'){
        const effective=kind==='ambiguous'?input.guidance_kind:kind;
        if((effective==='design'||effective==='thesis')&&typeof input.guidance_students==='number'&&input.guidance_students>=0){
          const rate=effective==='design'?12:8;
          hours=input.guidance_students*rate;
          formula=`${input.guidance_students}生 × ${rate}课时/生`;
        }
      }else{
        const total=actualHours(task);
        if(kind==='shared'){
          const span=Number(task.end_week)-Number(task.start_week)+1;
          if(typeof input.weeks==='number'&&input.weeks>=0&&span>0){
            const weeks=Math.min(input.weeks,span);
            hours=total*(weeks/span);
            formula=`${total}课时 × ${weeks}/${span}周`;
          }
        }else{
          hours=total;
          formula=`${total}课时`;
        }
      }
    }
    return {id,task,kind,hours:hours===null?null:Number(hours.toFixed(2)),formula};
  });
  return {rows,total:Number(rows.reduce((sum,row)=>sum+(row.hours??0),0).toFixed(2)),
    pending:rows.filter(row=>row.hours===null).length};
}
