export function stageLanes<T extends {id:number;start_week:number;end_week:number}>(tasks:T[]):{task:T;lane:number}[]{
  const ends:number[]=[];
  return [...tasks].sort((a,b)=>a.start_week-b.start_week||a.id-b.id).map(task=>{
    let lane=ends.findIndex(end=>end<task.start_week);if(lane<0)lane=ends.length;
    ends[lane]=task.end_week;return {task,lane};
  });
}
export function dropWeek(clientX:number,left:number,width:number):number{
  return Math.max(1,Math.min(20,Math.floor((clientX-left)/width*20)+1));
}
