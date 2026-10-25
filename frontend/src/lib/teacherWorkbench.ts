export type AcademicPeriod = {academic_year:string;academic_term:number};

export function openSelectionPlans<T extends {state:string;deadline:string;can_resubmit?:boolean}>(plans:T[],now=Date.now()):T[]{
  return plans.filter(plan=>(plan.state==='open'&&Date.parse(plan.deadline)>now)||(['open','matched'].includes(plan.state)&&plan.can_resubmit));
}

export function periodKey(period:AcademicPeriod):string{
  return `${period.academic_year}:${period.academic_term}`;
}

export function timetablePeriods(batches:{plan:AcademicPeriod}[],current:AcademicPeriod):AcademicPeriod[]{
  const historical=new Map(batches.map(({plan})=>[periodKey(plan),{academic_year:plan.academic_year,academic_term:plan.academic_term}]));
  historical.delete(periodKey(current));
  return [current,...[...historical.values()].sort((a,b)=>periodKey(b).localeCompare(periodKey(a)))];
}
