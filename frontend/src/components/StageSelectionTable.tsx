import { Button, Checkbox, Empty, Grid, Modal } from 'antd';
import { weekDates } from '../lib/selectionGrid';
import { examWeeksFor } from '../lib/examWeeks';
import { gradeLabel, stageClassScope, stageLanes, stageRoomLabel, stageRowMetrics } from '../lib/adminStageGrid';

export default function StageSelectionTable({plan,tasks,selected,onTask,onToggle,disabled,readOnly=false}:{plan:any;tasks:any[];selected:number[];onTask:(task:any,week:number)=>void;onToggle:(task:any)=>void;disabled:boolean;readOnly?:boolean}){
  const screens = Grid.useBreakpoint();
  const mobile = !screens.md;
  const fixedWidth = mobile ? 80 : 304;
  const groups:string[]=plan.groups?.length?plan.groups:[...new Set<string>(tasks.map(t=>t.group))];
  const weeks=Array.from({length:plan.weeks},(_,i)=>i+1);
  if(!groups.length)return <Empty description="该周期暂无班级"/>;
  const cohortFor=(group:string)=>{const groupTasks=tasks.filter(t=>t.group===group);return stageClassScope(group,plan.class_scopes||[],groupTasks).cohort||plan.cohort;};
  const cohortStart=(cohort:string)=>plan.cohort_calendar_rules?.[String(cohort||'').replace(/(?:级|届)$/,'')]?.start_date||plan.start_date;
  const startDates=new Set(groups.map(group=>cohortStart(cohortFor(group))));
  return <div className={`selection-stage-view${mobile ? ' is-mobile' : ''}`}>
    {mobile && <p className="stage-scroll-hint">左右滑动查看周次 · 点击课程查看详情</p>}
    <div className="stage-table-scroll" tabIndex={0} role="region" aria-label="可横向滚动的阶段课表">
    <table className="college-stage-table" aria-label={`${plan.major||'学院课程'}阶段${readOnly?'课表':'选课表'}`} style={{minWidth:fixedWidth+plan.weeks*64}}>
      <colgroup>{mobile ? <col style={{width:80}}/> : <><col style={{width:68}}/><col style={{width:110}}/><col style={{width:126}}/></>}{weeks.map(w=><col key={w}/>)}</colgroup>
      <thead><tr>{mobile ? <th rowSpan={2}>班级</th> : <><th rowSpan={2}>年级</th><th rowSpan={2}>专业</th><th rowSpan={2}>开课班级</th></>}{weeks.map(w=><th key={w}>第{w}周</th>)}</tr>
        <tr>{weeks.map(w=><th key={w} className="week-date">{startDates.size===1?weekDates([...startDates][0],w):'各年级分别设置'}</th>)}</tr></thead>
      <tbody>{groups.map(group=>{
        const groupTasks=tasks.filter(t=>t.group===group);
        const scope=stageClassScope(group,plan.class_scopes||[],groupTasks);
        const bars=stageLanes<any>(groupTasks.filter(t=>t.start_week&&t.end_week));
        const {laneStep,rowHeight}=stageRowMetrics(bars);
        const exams=examWeeksFor(plan,scope.cohort||plan.cohort,group,plan.weeks);
        return <tr key={group}>
          {mobile ? <th className="scope-cell mobile-scope-cell" style={{left:0}}><Button type="text" className="mobile-scope-button" aria-label={`查看班级信息 ${group}`} onClick={() => Modal.info({title:group,content:<div><p>年级：{gradeLabel(scope.cohort||plan.cohort)||'未注明'}</p><p>专业：{scope.major||plan.major||'未注明'}</p><p>开学日期：{cohortStart(scope.cohort||plan.cohort)||'未注明'}</p></div>})}><strong>{group}</strong><span>{gradeLabel(scope.cohort||plan.cohort)||'—'}</span><span>{scope.major||plan.major||'未注明专业'}</span></Button></th> : <>
          <th className="scope-cell" style={{left:0}}>{gradeLabel(scope.cohort||plan.cohort)||'—'}<div style={{fontSize:11,fontWeight:400}}>{cohortStart(scope.cohort||plan.cohort)}</div></th>
          <th className="scope-cell" style={{left:68}} title={scope.major}>{scope.major||plan.major||'—'}</th>
          <th className="scope-cell" style={{left:178}} title={group}>{group}</th>
          </>}
          <td colSpan={plan.weeks} style={{padding:0}}><div style={{position:'relative',height:rowHeight}}>
            {weeks.map(w=><div key={w} className={`stage-week-cell${exams.has(w)?' is-exam':''}`} style={{left:`${(w-1)*100/plan.weeks}%`,width:`${100/plan.weeks}%`}}>{exams.has(w)?'考试':''}</div>)}
            {bars.map(({task,lane})=><div key={task.id} className={`selection-course${selected.includes(task.id)?' is-selected':''}`} data-task-id={task.id} data-start-week={task.start_week} data-end-week={task.end_week}
              style={{left:`${(task.start_week-1)*100/plan.weeks}%`,width:`${(task.end_week-task.start_week+1)*100/plan.weeks}%`,top:lane*laneStep+2}}>
              <Button type="text" title={task.name} aria-label={`查看课程 ${task.name} ${task.group}`} onClick={()=>onTask(task,task.start_week)} className="selection-course-title">{task.name}</Button>
              <div className="course-secondary" title={task.teacher_names?.join('、')}>{task.teacher_names?.filter(Boolean).join('、')||'教师待分配'}</div>
              <div className="course-secondary">{stageRoomLabel(task.room_name)}</div>
              {!readOnly&&!mobile&&<Checkbox aria-label={`预选 ${plan.id} ${task.name} ${task.group}`} checked={selected.includes(task.id)} disabled={disabled} onChange={()=>onToggle(task)}>预选</Checkbox>}
            </div>)}
          </div></td>
        </tr>;
      })}</tbody>
    </table>
    </div>
  </div>;
}
