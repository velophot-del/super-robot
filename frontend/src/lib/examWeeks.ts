export function examWeeksFor(plan:any, cohort?:string|null, group?:string|null, weeks?:number):Set<number>{
  const total=Number(weeks??plan?.weeks??20)||20;
  const config=plan?.exam_weeks;
  if(config===undefined||config===null)return new Set([total]);
  if(typeof config!=='object'||Array.isArray(config))return new Set([total]);
  if(Object.keys(config).length===0)return new Set<number>();
  for(const key of [cohort,plan?.cohort,group,'*']){
    if(key&&Object.prototype.hasOwnProperty.call(config,String(key))){
      const list=config[String(key)];
      return new Set((Array.isArray(list)?list:[]).map(Number).filter((week:number)=>week>=1&&week<=total));
    }
  }
  return new Set([total]);
}
