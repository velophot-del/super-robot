import { normalizeCohort } from './adminStageGrid.ts';

function scopeKey(value:unknown):string{
  const text=String(value??'').trim();
  return /^\d{2,4}(?:级|届)?$/.test(text)?normalizeCohort(text):text;
}

function normalizedConfig(config:Record<string,unknown>):Map<string,number[]>{
  const result=new Map<string,number[]>();
  for(const [rawKey,rawWeeks] of Object.entries(config)){
    const key=scopeKey(rawKey);
    const weeks=Array.isArray(rawWeeks)?rawWeeks.map(Number).filter(Number.isFinite):[];
    result.set(key,[...new Set([...(result.get(key)||[]),...weeks])].sort((a,b)=>a-b));
  }
  return result;
}

export function examWeeksFor(plan:any, cohort?:string|null, group?:string|null, weeks?:number):Set<number>{
  const total=Number(weeks??plan?.weeks??20)||20;
  const config=plan?.exam_weeks;
  if(config===undefined||config===null)return new Set([total]);
  if(typeof config!=='object'||Array.isArray(config))return new Set([total]);
  if(Object.keys(config).length===0)return new Set<number>();
  const normalized=normalizedConfig(config);
  for(const key of [scopeKey(cohort),scopeKey(plan?.cohort),String(group??'').trim(),'*']){
    if(key&&normalized.has(key))return new Set(normalized.get(key)!.filter(week=>week>=1&&week<=total));
  }
  return new Set([total]);
}
