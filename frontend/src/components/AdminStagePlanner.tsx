import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AutoComplete, Button, Card, Empty, Input, InputNumber, Popconfirm, Select, Space, Tag, Typography, message } from 'antd';
import { MinusOutlined, PlusOutlined } from '@ant-design/icons';
import { planningApi as api } from '../api/planning';
import { weekDates } from '../lib/selectionGrid';
import { examWeeksFor } from '../lib/examWeeks';
import { stageLanes,dropWeek } from '../lib/adminStageGrid';

type DragItem={course_id?:number;task_id?:number;document_id?:number;duration?:number};
const MIME='application/x-college-stage';

export default function AdminStagePlanner({plan,rooms,classes=[],onChange,onEdit}:{plan:any;rooms:any[];classes?:any[];onChange:()=>Promise<void>;onEdit:(task:any)=>void}){
  const [pool,setPool]=useState<any[]>([]),[docId,setDocId]=useState<number>(),[search,setSearch]=useState(''),[groups,setGroups]=useState<string[]>([]);
  const [newGroup,setNewGroup]=useState(''),[removeGroup,setRemoveGroup]=useState<string>();
  const [selected,setSelected]=useState<DragItem>(),[duration,setDuration]=useState<Record<number,number|undefined>>({}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const pointer=useRef<{item:DragItem;name:string}|null>(null);
  const [ghost,setGhost]=useState<{x:number;y:number;name:string}>();
  const weeks=Number(plan.weeks)||20;
  const cellWidth=100/weeks;
  const cohorts=[...new Set<string>([
    ...(plan.tasks||[]).map((task:any)=>task.cohort).filter(Boolean),
    ...(plan.exam_weeks?Object.keys(plan.exam_weeks):[]),
    plan.cohort,
  ].filter(Boolean))];
  if(!cohorts.length)cohorts.push('*');
  const cohortKey=cohorts.join('|');
  const defaultExamDraft=()=>Object.fromEntries(cohorts.map((cohort:string)=>{
    if(plan.exam_weeks===undefined||plan.exam_weeks===null)return [cohort,[weeks]];
    if(Object.keys(plan.exam_weeks).length===0)return [cohort,[]];
    if(Object.prototype.hasOwnProperty.call(plan.exam_weeks,cohort))return [cohort,plan.exam_weeks[cohort]||[]];
    if(Object.prototype.hasOwnProperty.call(plan.exam_weeks,'*'))return [cohort,plan.exam_weeks['*']||[]];
    return [cohort,[weeks]];
  }));
  const [examDraft,setExamDraft]=useState<Record<string,number[]>>(()=>defaultExamDraft());
  useEffect(()=>{setExamDraft(defaultExamDraft());},[plan.id,plan.revision,weeks,cohortKey,JSON.stringify(plan.exam_weeks||{})]);
  const groupExam=(group:string)=>examWeeksFor(plan,(plan.tasks||[]).find((task:any)=>task.group===group)?.cohort,group,weeks);
  const editable=plan.state==='draft';
  const canEditGroups=plan.state!=='published';
  const canSetRoom=plan.state==='open'||plan.state==='matched';
  const groupKey=(plan.groups?.length?plan.groups:[...new Set<string>((plan.tasks||[]).map((t:any)=>t.group))]).join('|');
  const [examCohort,setExamCohort]=useState<string>(()=>cohorts[0]||'*');
  useEffect(()=>{setExamCohort(c=>cohorts.includes(c)?c:(cohorts[0]||'*'));},[cohortKey]);
  const toggleExamWeek=(week:number)=>{
    if(!editable)return;
    setExamDraft(draft=>{const cur=new Set(draft[examCohort]||[]);if(cur.has(week))cur.delete(week);else cur.add(week);return {...draft,[examCohort]:[...cur].sort((a,b)=>a-b)};});
  };
  const saveExam=async()=>{
    setBusy(true);
    try{await api.saveExamWeeks(plan.id,{exam_weeks:examDraft});message.success('考试周已保存');await onChange();}
    catch(e){message.error(e instanceof Error?e.message:'考试周保存失败');}
    finally{setBusy(false);}
  };
  useEffect(()=>{setGroups(groupKey?groupKey.split('|'):[]);},[groupKey]);
  const loadPool=useCallback(async()=>{
    try{const data=await api.coursePool(plan.id);setPool(data.courses);setDocId(data.document_id);setError('');}
    catch(e){setPool([]);setError(e instanceof Error?e.message:'课程列表读取失败');}
  },[plan.id]);
  useEffect(()=>{let active=true;void api.coursePool(plan.id).then(data=>{if(active){setPool(data.courses);setDocId(data.document_id);setError('');}}).catch(e=>{if(active)setError(e instanceof Error?e.message:'课程列表读取失败');});return()=>{active=false;};},[plan.id,plan.revision]);
  const action=async(fn:()=>Promise<unknown>)=>{setBusy(true);try{await fn();await onChange();message.success('课表已保存');}catch(e){message.error(e instanceof Error?e.message:'操作失败，请刷新核对');}finally{setBusy(false);}};
  const updateGroups=async(next:string[])=>{
    setBusy(true);
    try{await api.savePlanGroups(plan.id,{revision:plan.revision,groups:next});await onChange();message.success('班级条目已更新');return true;}
    catch(e){message.error(e instanceof Error?e.message:'班级保存失败');return false;}
    finally{setBusy(false);}
  };
  const addGroupRow=async()=>{
    const name=newGroup.trim();
    if(!name)return;
    if(groups.includes(name)){message.info('该班级已在课表中');return;}
    if(await updateGroups([...groups,name]))setNewGroup('');
  };
  const removeGroupRow=async()=>{
    if(!removeGroup)return;
    if(await updateGroups(groups.filter(group=>group!==removeGroup)))setRemoveGroup(undefined);
  };
  const place=(group:string,week:number,item=selected)=>{
    if(!editable||busy||!item)return;
    if(item.course_id&&!item.duration){message.warning('请先填写该课程占用周数，方案未提供时不能猜定');return;}
    if(week>weeks){message.warning('不在周期内');return;}
    const moving=(plan.tasks||[]).find((task:any)=>task.id===item.task_id);
    const span=item.task_id?(moving?(moving.end_week-moving.start_week+1):1):(item.duration||1);
    const blocked=[...groupExam(group)].filter(examWeek=>examWeek>=week&&examWeek<week+span).sort((a,b)=>a-b);
    if(blocked.length){message.warning(`第${blocked.join('、')}周为该年级考试周，不能安排课程`);return;}
    void action(()=>api.placeCourse(plan.id,{...item,revision:plan.revision,group,start_week:week}));
  };
  const drag=(e:React.DragEvent,item:DragItem)=>{e.dataTransfer.setData(MIME,JSON.stringify(item));e.dataTransfer.effectAllowed='move';setSelected(item);};
  const beginPointer=(e:React.PointerEvent<HTMLElement>,item:DragItem,name:string)=>{
    if(!editable||busy)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);
    pointer.current={item,name};setGhost({x:e.clientX,y:e.clientY,name});
  };
  const endPointer=(e:React.PointerEvent<HTMLElement>)=>{
    const current=pointer.current;pointer.current=null;setGhost(undefined);
    if(!current)return;
    const target=document.elementFromPoint(e.clientX,e.clientY)?.closest<HTMLElement>('[data-stage-group]');
    if(target){const box=target.getBoundingClientRect();place(target.dataset.stageGroup!,dropWeek(e.clientX,box.left,box.width,weeks),current.item);}
  };
  const sync=async()=>{setBusy(true);try{const r=await api.syncCoursePool(plan.id);await loadPool();message.success(`课程库新增${r.added}门，复用${r.reused}门`);}catch(e){message.error(e instanceof Error?e.message:'同步失败');}finally{setBusy(false);}};
  const configuredGroups=plan.groups?.length?plan.groups:[...new Set<string>((plan.tasks||[]).map((t:any)=>t.group))];
  const placed=(plan.tasks||[]).filter((t:any)=>t.start_week&&t.end_week);
  const pending=(plan.tasks||[]).filter((t:any)=>!t.start_week);
  return <Space orientation="vertical" style={{width:'100%'}} size="middle">
    {ghost&&<div style={{position:'fixed',left:ghost.x+14,top:ghost.y+14,pointerEvents:'none',zIndex:2000,background:'#7654ec',color:'white',padding:'8px 12px',borderRadius:6}}>{ghost.name}</div>}
    <Alert showIcon type="info" title={`按班级和${weeks}周编排阶段课程`} description="从课程列表拖到班级对应的起始周，按方案上课周数形成课程块。也可点“选择放置”，再点目标周。拖动课程块可调整周段或班级；点击课程名称维护教师名额。考试周按年级设置（顶部工具栏选择年级后在表头点选周次）。周内节次为可选项，发布前核验周段、地点、教师与教学组冲突。"/>
    {error&&<Alert showIcon type="error" title={error}/>}
    <div style={{display:'flex',gap:16,alignItems:'flex-start',flexWrap:'wrap'}}>
      <Card title="本周期课程列表" size="small" style={{width:280,flexShrink:0}} extra={<Button size="small" loading={busy} disabled={!docId} onClick={()=>void sync()}>同步课程库</Button>}>
        <Typography.Paragraph type="secondary">{plan.global_cycle?`全学院 · 第${plan.academic_term}学期 · 所有年级与专业`:`生效方案 · ${plan.major||'未设置专业'} · ${plan.cohort||'未设置届次'}级 · 第${plan.semester}学期`}</Typography.Paragraph>
        <Input.Search aria-label="搜索待排课程" placeholder="课程名称或编码" value={search} onChange={e=>setSearch(e.target.value)} style={{marginBottom:12}}/>
        {!pool.length&&<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={docId?'本学期暂无可排专业课程，请同步或核对方案':plan.global_cycle?'请先在培养方案页面启用至少一个方案':'请先启用该专业届次培养方案'}/>}
        <div style={{maxHeight:640,overflowY:'auto'}}>{pool.filter(c=>`${c.name} ${c.code}`.includes(search)).map(course=>{
          const weeks=duration[course.id]??course.teaching_weeks;
          const item={course_id:course.id,document_id:course.document_id,duration:weeks||undefined};
          return <div key={course.id} draggable={editable&&!busy} onDragStart={e=>drag(e,item)} style={{border:`1px solid ${selected?.course_id===course.id?'#7654ec':'#e4e1ed'}`,background:'#faf9ff',borderRadius:6,padding:10,marginBottom:10,cursor:editable?'grab':'default'}}>
            <Typography.Text strong>{course.name}</Typography.Text><Button size="small" style={{display:'block',marginTop:5,touchAction:'none',cursor:'grab'}} disabled={!editable||busy} aria-label={`拖拽放置 ${course.name}`} onPointerDown={e=>beginPointer(e,item,course.name)} onPointerMove={e=>{if(pointer.current)setGhost({x:e.clientX,y:e.clientY,name:pointer.current.name});}} onPointerUp={endPointer} onPointerCancel={()=>{pointer.current=null;setGhost(undefined);}}>拖拽放置</Button>
            {course.major&&<div style={{fontSize:11,color:'#7654ec',marginTop:4}}>{course.major} · {course.cohort}级 · 第{course.semester}学期</div>}
            <div style={{fontSize:12,margin:'4px 0'}}>{course.credits}学分 · {course.required_hours}学时 · {course.weekly_hours??'未注明'}节/周</div>
            <Space wrap><label>占用 <InputNumber aria-label={`${course.name}占用周数`} min={1} max={plan.weeks-1} value={weeks} onChange={v=>setDuration(current=>({...current,[course.id]:v??undefined}))} style={{width:60}} disabled={!editable||busy}/> 周</label><Button size="small" disabled={!editable||busy} onClick={()=>{setSelected(item);message.info('请点击班级行中的起始周');}}>选择放置</Button></Space>
            {course.notes&&<Typography.Paragraph type="secondary" style={{fontSize:11,margin:'5px 0 0'}}>{course.notes}</Typography.Paragraph>}
          </div>;
        })}</div>
      </Card>
      <div style={{flex:'1 1 620px',minWidth:0}}>
        {selected&&<Alert type="success" style={{marginBottom:10}} title="已选择课程：点击班级中的起始周，或直接拖拽放置" action={<Button size="small" onClick={()=>setSelected(undefined)}>取消选择</Button>}/>}
        {editable&&<div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap',marginBottom:10,padding:'8px 10px',background:'#f6f3ff',border:'1px solid #e4ddfb',borderRadius:8}}>
          <Typography.Text strong>考试周设置</Typography.Text>
          <Select size="small" aria-label="选择年级" value={examCohort} onChange={setExamCohort} style={{width:160}} options={cohorts.map((c:string)=>({value:c,label:c==='*'?'默认（全部年级）':`${c}级`}))}/>
          <Button size="small" type="primary" loading={busy} onClick={()=>void saveExam()}>保存考试周</Button>
          <Typography.Text type="secondary" style={{fontSize:12}}>在下方表头第3行点选周次，切换该年级的考试周；全部取消则该年级无考试周。</Typography.Text>
        </div>}
        {!configuredGroups.length?<Empty description="先添加并保存开课班级，即可出现空白课表"/>:<div style={{overflowX:'auto',border:'1px solid #ddd',borderRadius:8}}><table aria-label={`管理员${weeks}周班级课表`} style={{borderCollapse:'collapse',width:'100%',minWidth:160+weeks*64,tableLayout:'fixed'}}>
          <colgroup><col style={{width:160}}/>{Array.from({length:weeks},(_,i)=><col key={i}/>)}</colgroup>
          <thead>
            <tr><th rowSpan={editable?3:2} style={{background:'#eee9fb',border:'1px solid #ddd'}}>开课班级</th>{Array.from({length:weeks},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:'8px 2px',background:'#eee9fb',fontSize:12}}>第{i+1}周</th>)}</tr>
            <tr>{Array.from({length:weeks},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:'5px 1px',fontSize:10,fontWeight:400}}>{weekDates(plan.start_date,i+1)}</th>)}</tr>
            {editable&&<tr>{Array.from({length:weeks},(_,i)=>{const w=i+1;const on=(examDraft[examCohort]||[]).includes(w);return <th key={i} style={{border:'1px solid #ddd',padding:2,background:on?'#fbe9e9':'#fff'}}><Button size="small" type={on?'primary':'default'} block aria-label={`切换 ${examCohort} 第${w}周考试周`} onClick={()=>toggleExamWeek(w)} style={{fontSize:11,padding:'0 2px',height:22}}>{on?'考试':'·'}</Button></th>;})}</tr>}
          </thead>
          <tbody>{configuredGroups.map((group:string)=>{
            const bars=stageLanes<any>(placed.filter((t:any)=>t.group===group)),height=Math.max(130,...bars.map(b=>(b.lane+1)*130));
            const examSet=groupExam(group);
            return <tr key={group}><th style={{border:'1px solid #ddd',padding:8,position:'sticky',left:0,background:'white',zIndex:2}}>{group}</th><td colSpan={weeks} style={{padding:0,border:'1px solid #ddd'}}>
              <div data-stage-group={group} style={{height,position:'relative'}} onDragOver={e=>{if(editable&&!busy&&e.dataTransfer.types.includes(MIME)){e.preventDefault();e.dataTransfer.dropEffect='move';}}} onDrop={e=>{e.preventDefault();try{const item=JSON.parse(e.dataTransfer.getData(MIME));const box=e.currentTarget.getBoundingClientRect();place(group,dropWeek(e.clientX,box.left,box.width,weeks),item);}catch{message.error('请从课程列表或现有课程块拖入');}}}>
                {Array.from({length:weeks},(_,i)=>{const w=i+1;const isExam=examSet.has(w);return <Button key={i} type="text" aria-label={`放置到 ${group} 第${w}周`} disabled={!editable||busy||isExam} onClick={()=>place(group,w)} style={{position:'absolute',left:`${i*cellWidth}%`,width:`${cellWidth}%`,height:'100%',borderRadius:0,borderRight:'1px solid #eee',background:isExam?'#fbe9e9':selected?'#faf8ff':'white',padding:0,color:'#bbb',fontSize:11}}>{isExam?'考试':selected?'+':''}</Button>;})}
                {bars.map(({task,lane})=><div key={task.id} draggable={editable&&!busy} onDragStart={e=>drag(e,{task_id:task.id})} style={{position:'absolute',left:`${(task.start_week-1)*cellWidth}%`,width:`${(task.end_week-task.start_week+1)*cellWidth}%`,top:lane*130+4,height:122,background:'#eee9ff',border:'1px solid #9e87d9',borderRadius:6,boxSizing:'border-box',padding:7,cursor:editable?'grab':'default',overflow:'auto'}}>
                  <Button type="text" onClick={()=>{if(editable)onEdit(task);}} style={{display:'block',whiteSpace:'normal',height:'auto',padding:0,fontWeight:600,textAlign:'left',width:'100%'}}>{task.name}</Button>
                  <div style={{fontSize:11,marginTop:4}}>W{task.start_week}—W{task.end_week} · {task.end_week-task.start_week+1}周</div><div style={{fontSize:11}}>{task.credits}学分 · {task.required_hours}学时</div><div style={{fontSize:11}}>{task.slots?.length?`已配节次 ${task.slots.length} 段`:'节次未配置（可选）'} · {task.room_name||'待配地点'}</div>
                  {canSetRoom&&<Select size="small" aria-label={`设置 ${task.name} ${group} 的上课地点`} style={{width:'100%',marginTop:4}} placeholder="设置上课地点（可选）" allowClear disabled={busy}
                    value={task.room_id??undefined} onChange={v=>void action(()=>api.setTaskRoom(plan.id,task.id,v??null))}
                    options={rooms.filter((r:any)=>r.is_available).map((r:any)=>({value:r.id,label:`${r.name} · ${r.capacity}座`}))}/>}
                  {editable&&<Popconfirm title="移回待排？保留来源课程记录。" onConfirm={()=>action(()=>api.unplaceCourse(plan.id,task.id,plan.revision))}><Button size="small" type="link" disabled={busy} style={{padding:0,fontSize:11}}>移回待排</Button></Popconfirm>}
                </div>)}
              </div>
            </td></tr>;
          })}</tbody>
        </table></div>}
      </div>
    </div>
    <Card size="small" title="班级条目" extra={<Space><Tag>已排{placed.length}项</Tag><Tag>待排{pending.length}项</Tag></Space>}>
      <Space wrap>
        <AutoComplete aria-label="新增班级名称" value={newGroup} onChange={setNewGroup} options={classes.map((row:any)=>({value:row.name,label:`${row.name}${row.department?` · ${row.department}`:''}`}))}
          placeholder="输入或选择班级" style={{width:240}} disabled={!canEditGroups||busy}/>
        <Button type="primary" icon={<PlusOutlined/>} disabled={!canEditGroups||busy||!newGroup.trim()} onClick={()=>void addGroupRow()}>增加班级</Button>
        <Select aria-label="选择要移除的班级" value={removeGroup} onChange={setRemoveGroup} placeholder="选择要移除的班级" allowClear
          options={groups.map(group=>({value:group,label:group}))} style={{width:240}} disabled={!canEditGroups||busy}/>
        <Popconfirm title={removeGroup?`移除班级「${removeGroup}」？已有排课任务的班级不能移除。`:'请选择要移除的班级'} onConfirm={()=>void removeGroupRow()} disabled={!removeGroup}>
          <Button danger icon={<MinusOutlined/>} disabled={!canEditGroups||busy||!removeGroup}>减少班级</Button>
        </Popconfirm>
        <Typography.Text type="secondary">增加或减少后立即更新课程表条目。</Typography.Text>
      </Space>
      {!canEditGroups&&<Alert type="info" showIcon title="已发布周期的班级条目已冻结" style={{marginTop:12}}/>}
      {canEditGroups&&plan.state!=='draft'&&<Alert type="warning" showIcon title="非草稿阶段新增班级不会自动生成课程任务" style={{marginTop:12}}/>}
    </Card>
  </Space>;
}
