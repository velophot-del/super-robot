export function calendarDate(value:string):Date|null{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const date=new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value?date:null;
}
export function suggestedMonday(value:string):string|undefined{
  const date=calendarDate(value);if(!date)return;
  date.setUTCDate(date.getUTCDate()-(date.getUTCDay()+6)%7);
  return date.toISOString().slice(0,10);
}
export function academicCalendar(start:string,weeks=20){
  const date=calendarDate(start);if(!date||date.getUTCDay()!==1)return [];
  return Array.from({length:weeks},(_,i)=>{
    const begin=new Date(date);begin.setUTCDate(begin.getUTCDate()+i*7);
    const end=new Date(begin);end.setUTCDate(end.getUTCDate()+6);
    // 最后一周为考试周，周数由周期设置决定，不能写死为第20周。
    return {week:i+1,start:begin.toISOString().slice(0,10),end:end.toISOString().slice(0,10),exam:i===weeks-1};
  });
}
