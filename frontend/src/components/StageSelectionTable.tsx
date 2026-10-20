import { Button, Checkbox, Empty, Tag, Typography } from 'antd';
import { selectionSegments,weekDates,selectionSlots } from '../lib/selectionGrid';

export default function StageSelectionTable({plan,tasks,selected,onTask,onToggle,disabled}:{plan:any;tasks:any[];selected:number[];onTask:(task:any,week:number)=>void;onToggle:(task:any)=>void;disabled:boolean}){
  const groups=[...new Set(tasks.map(t=>t.group))].sort();
  const weeks=Array.from({length:plan.weeks},(_,i)=>i+1);
  if(!groups.length)return <Empty description="该周期暂无课程任务"/>;
  return <div style={{overflowX:'auto',border:'1px solid #d9d9e3',borderRadius:8}}>
    <table aria-label={`${plan.major||'专业课程'}阶段选课表`} style={{borderCollapse:'collapse',tableLayout:'fixed',width:'100%',minWidth:240+plan.weeks*66}}>
      <colgroup><col style={{width:100}}/><col style={{width:140}}/>{weeks.map(w=><col key={w}/>)}</colgroup>
      <thead>
        <tr style={{background:'#f2f0fb'}}><th rowSpan={2} style={{border:'1px solid #d9d9e3',padding:8}}>专业 / 年级</th><th rowSpan={2} style={{border:'1px solid #d9d9e3',padding:8}}>教学组 / 班级</th>{weeks.map(w=><th key={w} style={{border:'1px solid #d9d9e3',padding:'8px 2px',fontSize:12}}>第{w}周</th>)}</tr>
        <tr style={{background:'#faf9fe'}}>{weeks.map(w=><th key={w} style={{border:'1px solid #d9d9e3',padding:'6px 2px',fontSize:11,fontWeight:400}}>{weekDates(plan.start_date,w)}</th>)}</tr>
      </thead>
      <tbody>{groups.map((group,index)=><tr key={group}>
        {index===0&&<th rowSpan={groups.length} style={{border:'1px solid #d9d9e3',padding:10,background:'#faf9fe'}}><div>{plan.major||'未注明专业'}</div><Typography.Text type="secondary">{plan.cohort?`${plan.cohort}级`:''}</Typography.Text></th>}
        <th style={{border:'1px solid #d9d9e3',padding:10,background:'white',position:'sticky',left:0,zIndex:1}}>{group}</th>
        {selectionSegments(tasks.filter(t=>t.group===group),plan.weeks).map(segment=><td key={segment.start} colSpan={segment.span} style={{verticalAlign:'top',border:'1px solid #d9d9e3',padding:5,background:segment.exam?'#f5f5f5':'white',height:110}}>
          {segment.tasks.length?segment.tasks.map(task=><div key={task.id} style={{border:`1px solid ${selected.includes(task.id)?'#7654ec':'#e7e3f0'}`,borderRadius:6,padding:6,marginBottom:5,background:selected.includes(task.id)?'#f3efff':'white'}}>
            <Button type="text" block aria-label={`查看课程 ${task.name} ${task.group}`} onClick={()=>onTask(task,segment.start)}
              style={{display:'block',height:'auto',minHeight:68,whiteSpace:'normal',textAlign:'left',padding:3,overflowWrap:'anywhere'}}>
              <div style={{fontWeight:600}}>{task.name}{selected.includes(task.id)?' ✓':''}</div>
              <div style={{fontSize:11,opacity:0.85}}>{selectionSlots(task,segment.start)}</div>
              <div style={{fontSize:11,opacity:0.85}}>{task.credits}学分 · {task.required_hours}学时</div>
              <div style={{fontSize:11,opacity:0.85}}>{task.teacher_names?.length?task.teacher_names.join('、'):'教师待分配'}</div>
            </Button>
            <Checkbox aria-label={`预选 ${plan.id} ${task.name} ${task.group}`} checked={selected.includes(task.id)} disabled={disabled} onChange={()=>onToggle(task)}>预选</Checkbox>
          </div>):segment.exam?<Tag>考试</Tag>:null}
        </td>)}
      </tr>)}</tbody>
    </table>
  </div>;
}
