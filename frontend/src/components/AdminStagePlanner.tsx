import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, Empty, Input, InputNumber, Popconfirm, Select, Space, Tag, Typography, message } from 'antd';
import { planningApi as api } from '../api/planning';
import { weekDates } from '../lib/selectionGrid';
import { stageLanes,dropWeek } from '../lib/adminStageGrid';

type DragItem={course_id?:number;task_id?:number;duration?:number};
const MIME='application/x-college-stage';

export default function AdminStagePlanner({plan,onChange,onEdit}:{plan:any;onChange:()=>Promise<void>;onEdit:(task:any)=>void}){
  const [pool,setPool]=useState<any[]>([]),[docId,setDocId]=useState<number>(),[search,setSearch]=useState(''),[groups,setGroups]=useState<string[]>([]);
  const [selected,setSelected]=useState<DragItem>(),[duration,setDuration]=useState<Record<number,number|undefined>>({}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const pointer=useRef<{item:DragItem;name:string}|null>(null);
  const [ghost,setGhost]=useState<{x:number;y:number;name:string}>();
  const editable=plan.state==='draft';
  const groupKey=(plan.groups?.length?plan.groups:[...new Set<string>((plan.tasks||[]).map((t:any)=>t.group))]).join('|');
  useEffect(()=>{setGroups(groupKey?groupKey.split('|'):[]);},[groupKey]);
  const loadPool=useCallback(async()=>{
    try{const data=await api.coursePool(plan.id);setPool(data.courses);setDocId(data.document_id);setError('');}
    catch(e){setPool([]);setError(e instanceof Error?e.message:'课程列表读取失败');}
  },[plan.id]);
  useEffect(()=>{let active=true;void api.coursePool(plan.id).then(data=>{if(active){setPool(data.courses);setDocId(data.document_id);setError('');}}).catch(e=>{if(active)setError(e instanceof Error?e.message:'课程列表读取失败');});return()=>{active=false;};},[plan.id,plan.revision]);
  const action=async(fn:()=>Promise<unknown>)=>{setBusy(true);try{await fn();await onChange();message.success('课表已保存');}catch(e){message.error(e instanceof Error?e.message:'操作失败，请刷新核对');}finally{setBusy(false);}};
  const place=(group:string,week:number,item=selected)=>{
    if(!editable||busy||!item)return;
    if(item.course_id&&!item.duration){message.warning('请先填写该课程占用周数，方案未提供时不能猜定');return;}
    if(week>plan.weeks-1){message.warning('此周为考试周或不在周期内');return;}
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
    if(target){const box=target.getBoundingClientRect();place(target.dataset.stageGroup!,dropWeek(e.clientX,box.left,box.width),current.item);}
  };
  const sync=async()=>{setBusy(true);try{const r=await api.syncCoursePool(plan.id);await loadPool();message.success(`课程库新增${r.added}门，复用${r.reused}门`);}catch(e){message.error(e instanceof Error?e.message:'同步失败');}finally{setBusy(false);}};
  const configuredGroups=plan.groups?.length?plan.groups:[...new Set<string>((plan.tasks||[]).map((t:any)=>t.group))];
  const placed=(plan.tasks||[]).filter((t:any)=>t.start_week&&t.end_week);
  const pending=(plan.tasks||[]).filter((t:any)=>!t.start_week);
  return <Space orientation="vertical" style={{width:'100%'}} size="middle">
    {ghost&&<div style={{position:'fixed',left:ghost.x+14,top:ghost.y+14,pointerEvents:'none',zIndex:2000,background:'#7654ec',color:'white',padding:'8px 12px',borderRadius:6}}>{ghost.name}</div>}
    <Alert showIcon type="info" title="按班级和20周编排阶段课程" description="从课程列表拖到班级对应的起始周，按方案上课周数形成课程块。也可点“选择放置”，再点目标周。拖动课程块可调整周段或班级；点击课程名称配置节次、尾周和地点。最后一周保留考试（20周周期为第20周），开放前校验实际学时与冲突。"/>
    {error&&<Alert showIcon type="error" title={error}/>}
    <Card size="small"><Space wrap><Typography.Text strong>开课班级</Typography.Text><Select aria-label="编排开课班级" mode="tags" tokenSeparators={['，',',']} style={{minWidth:360,maxWidth:'100%'}} value={groups} onChange={setGroups} disabled={!editable||busy} options={configuredGroups.map((g:string)=>({value:g,label:g}))}/><Button disabled={!editable||busy} onClick={()=>void action(()=>api.savePlanGroups(plan.id,{revision:plan.revision,groups}))}>保存班级</Button><Tag>已排{placed.length}项</Tag><Tag>待排{pending.length}项</Tag><Tag color="orange">待补节次{placed.filter((t:any)=>!t.slots?.length).length}项</Tag></Space></Card>
    <div style={{display:'flex',gap:16,alignItems:'flex-start',flexWrap:'wrap'}}>
      <Card title="本周期课程列表" size="small" style={{width:280,flexShrink:0}} extra={<Button size="small" loading={busy} disabled={!docId} onClick={()=>void sync()}>同步课程库</Button>}>
        <Typography.Paragraph type="secondary">生效方案 · {plan.major||'未设置专业'} · {plan.cohort||'未设置届次'}级 · 第{plan.semester}学期</Typography.Paragraph>
        <Input.Search aria-label="搜索待排课程" placeholder="课程名称或编码" value={search} onChange={e=>setSearch(e.target.value)} style={{marginBottom:12}}/>
        {!pool.length&&<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={docId?'暂无本学期可排专业课程，请同步或核对方案':'请先启用该专业届次培养方案'}/>}
        <div style={{maxHeight:640,overflowY:'auto'}}>{pool.filter(c=>`${c.name} ${c.code}`.includes(search)).map(course=>{
          const weeks=duration[course.id]??course.teaching_weeks;
          const item={course_id:course.id,duration:weeks||undefined};
          return <div key={course.id} draggable={editable&&!busy} onDragStart={e=>drag(e,item)} style={{border:`1px solid ${selected?.course_id===course.id?'#7654ec':'#e4e1ed'}`,background:'#faf9ff',borderRadius:6,padding:10,marginBottom:10,cursor:editable?'grab':'default'}}>
            <Typography.Text strong>{course.name}</Typography.Text><Button size="small" style={{display:'block',marginTop:5,touchAction:'none',cursor:'grab'}} disabled={!editable||busy} aria-label={`拖拽放置 ${course.name}`} onPointerDown={e=>beginPointer(e,item,course.name)} onPointerMove={e=>{if(pointer.current)setGhost({x:e.clientX,y:e.clientY,name:pointer.current.name});}} onPointerUp={endPointer} onPointerCancel={()=>{pointer.current=null;setGhost(undefined);}}>拖拽放置</Button><div style={{fontSize:12,margin:'4px 0'}}>{course.credits}学分 · {course.required_hours}学时 · {course.weekly_hours??'未注明'}节/周</div>
            <Space wrap><label>占用 <InputNumber aria-label={`${course.name}占用周数`} min={1} max={plan.weeks-1} value={weeks} onChange={v=>setDuration(current=>({...current,[course.id]:v??undefined}))} style={{width:60}} disabled={!editable||busy}/> 周</label><Button size="small" disabled={!editable||busy} onClick={()=>{setSelected(item);message.info('请点击班级行中的起始周');}}>选择放置</Button></Space>
            {course.notes&&<Typography.Paragraph type="secondary" style={{fontSize:11,margin:'5px 0 0'}}>{course.notes}</Typography.Paragraph>}
          </div>;
        })}</div>
      </Card>
      <div style={{flex:'1 1 620px',minWidth:0}}>
        {selected&&<Alert type="success" style={{marginBottom:10}} title="已选择课程：点击班级中的起始周，或直接拖拽放置" action={<Button size="small" onClick={()=>setSelected(undefined)}>取消选择</Button>}/>}
        {!configuredGroups.length?<Empty description="先添加并保存开课班级，即可出现空白课表"/>:<div style={{overflowX:'auto',border:'1px solid #ddd',borderRadius:8}}><table aria-label="管理员20周班级课表" style={{borderCollapse:'collapse',width:'100%',minWidth:1480,tableLayout:'fixed'}}>
          <colgroup><col style={{width:160}}/>{Array.from({length:20},(_,i)=><col key={i}/>)}</colgroup>
          <thead><tr><th rowSpan={2} style={{background:'#eee9fb',border:'1px solid #ddd'}}>开课班级</th>{Array.from({length:20},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:'8px 2px',background:i>=plan.weeks-1?'#eee':'#eee9fb',fontSize:12}}>第{i+1}周</th>)}</tr><tr>{Array.from({length:20},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:'5px 1px',fontSize:10,fontWeight:400}}>{weekDates(plan.start_date,i+1)}</th>)}</tr></thead>
          <tbody>{configuredGroups.map((group:string)=>{
            const bars=stageLanes<any>(placed.filter((t:any)=>t.group===group)),height=Math.max(130,...bars.map(b=>(b.lane+1)*130));
            return <tr key={group}><th style={{border:'1px solid #ddd',padding:8,position:'sticky',left:0,background:'white',zIndex:2}}>{group}</th><td colSpan={20} style={{padding:0,border:'1px solid #ddd'}}>
              <div data-stage-group={group} style={{height,position:'relative'}} onDragOver={e=>{if(editable&&!busy&&e.dataTransfer.types.includes(MIME)){e.preventDefault();e.dataTransfer.dropEffect='move';}}} onDrop={e=>{e.preventDefault();try{const item=JSON.parse(e.dataTransfer.getData(MIME));const box=e.currentTarget.getBoundingClientRect();place(group,dropWeek(e.clientX,box.left,box.width),item);}catch{message.error('请从课程列表或现有课程块拖入');}}}>
                {Array.from({length:20},(_,i)=><Button key={i} type="text" aria-label={`放置到 ${group} 第${i+1}周`} disabled={!editable||busy||i>=plan.weeks-1} onClick={()=>place(group,i+1)} style={{position:'absolute',left:`${i*5}%`,width:'5%',height:'100%',borderRadius:0,borderRight:'1px solid #eee',background:i>=plan.weeks-1?'#f3f3f3':selected?'#faf8ff':'white',padding:0,color:'#bbb',fontSize:11}}>{i>=plan.weeks-1?'考试':selected?'+':''}</Button>)}
                {bars.map(({task,lane})=><div key={task.id} draggable={editable&&!busy} onDragStart={e=>drag(e,{task_id:task.id})} style={{position:'absolute',left:`${(task.start_week-1)*5}%`,width:`${(task.end_week-task.start_week+1)*5}%`,top:lane*130+4,height:122,background:task.slots?.length?'#eee9ff':'#fff4df',border:'1px solid #9e87d9',borderRadius:6,boxSizing:'border-box',padding:7,cursor:editable?'grab':'default',overflow:'auto'}}>
                  <Button type="text" onClick={()=>onEdit(task)} style={{display:'block',whiteSpace:'normal',height:'auto',padding:0,fontWeight:600,textAlign:'left',width:'100%'}}>{task.name}</Button>
                  <div style={{fontSize:11,marginTop:4}}>W{task.start_week}—W{task.end_week} · {task.end_week-task.start_week+1}周</div><div style={{fontSize:11}}>{task.credits}学分 · {task.required_hours}学时</div><div style={{fontSize:11}}>{task.slots?.length?'已配节次':'待配节次'} · {task.room_name||'待配地点'}</div>
                  {editable&&<Button type="link" size="small" disabled={busy} aria-label={`设置 ${task.name} ${group} 的节次与地点`} onClick={()=>onEdit(task)} style={{padding:0,height:22}}>设置节次与地点</Button>}
                  {editable&&<Popconfirm title="移回待排？保留来源课程记录。" onConfirm={()=>action(()=>api.unplaceCourse(plan.id,task.id,plan.revision))}><Button size="small" type="link" disabled={busy} style={{padding:0,fontSize:11}}>移回待排</Button></Popconfirm>}
                </div>)}
              </div>
            </td></tr>;
          })}</tbody>
        </table></div>}
      </div>
    </div>
  </Space>;
}
