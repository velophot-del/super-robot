import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Empty, Modal, Result, Select, Space, Spin, Table, Tabs, Tag, Typography, message } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { Link, Navigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi as api } from '../api/planning';
import { academicYear,filterSelectionPlans,selectionSlots } from '../lib/selectionGrid';
import StageSelectionTable from '../components/StageSelectionTable';
import ProfessionalExport from '../components/ProfessionalExport';

const statusNames:Record<string,string>={open:'开放选课',matched:'匹配审核中',published:'已发布'};
const editable=(p:any)=>p.state==='open'&&new Date(p.deadline).getTime()>Date.now();

export default function TeacherSelectionPage(){
  const {user}=useAuth();
  const [plans,setPlans]=useState<any[]>([]),[states,setStates]=useState<Record<number,any>>({});
  const [year,setYear]=useState(''),[term,setTerm]=useState('all'),[major,setMajor]=useState('all');
  const [ready,setReady]=useState<boolean>(),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [detail,setDetail]=useState<{planId:number;task:any;week:number}>(),[tab,setTab]=useState('pool');
  const teaching=can(user,'teaching');
  const bootstrap=useCallback(async()=>{
    if(!teaching)return;setLoading(true);setError('');
    try{
      const personal=await api.selfProfile();setReady(personal.ready);if(!personal.ready)return;
      const list=await api.plans();setPlans(list);
      setYear(current=>list.some((p:any)=>(p.academic_year||academicYear(p.start_date))===current)?current:
        (()=>{const first=list.find(editable)||list[0];return first?(first.academic_year||academicYear(first.start_date)):'';})());
    }catch(e){setError(e instanceof Error?e.message:'读取选课信息失败');}finally{setLoading(false);}
  },[teaching]);
  useEffect(()=>{void bootstrap();},[bootstrap]);
  const filtered=useMemo(()=>filterSelectionPlans(plans,year,term,major),[plans,year,term,major]);
  const ids=filtered.map(p=>p.id).join(',');
  const [gridLoading,setGridLoading]=useState(false),[refresh,setRefresh]=useState(0);
  useEffect(()=>{
    let active=true;const numbers=ids?ids.split(',').map(Number):[];
    setStates({});setDetail(undefined);
    if(!numbers.length){setGridLoading(false);return()=>{active=false;};}
    setGridLoading(true);setError('');
    void Promise.allSettled(numbers.map(id=>api.state(id))).then(results=>{
      if(!active)return;const loaded:Record<number,any>={};let failed=0;
      results.forEach((r,i)=>{if(r.status==='fulfilled')loaded[numbers[i]]=r.value;else failed++;});
      setStates(loaded);if(failed)setError(`${failed}个周期读取失败，请点击刷新重试；未加载的课程不会被提交。`);setGridLoading(false);
    });return()=>{active=false;};
  },[ids,refresh]);
  const currentPlans=filtered.map(p=>states[p.id]).filter(Boolean);
  const years=[...new Set(plans.map(p=>p.academic_year||academicYear(p.start_date)))].sort().reverse();
  const majors=[...new Set(plans.filter(p=>(p.academic_year||academicYear(p.start_date))===year).map(p=>p.major).filter(Boolean))].sort();
  const save=async(plan:any,taskIds:number[])=>{
    setBusy(true);
    try{const draft=await api.saveDraft(plan.id,{revision:plan.draft.revision,plan_revision:plan.revision,task_ids:taskIds});setStates(current=>({...current,[plan.id]:{...plan,draft}}));message.success('已保存个人草稿');}
    catch(e){message.error(e instanceof Error?e.message:'保存失败，请刷新后核对');}finally{setBusy(false);}
  };
  const toggle=async(plan:any,task:any)=>{
    const choices:number[]=plan.draft.task_ids;
    if(!choices.includes(task.id)&&choices.length>=5){message.warning('每个周期最多5项志愿');return;}
    await save(plan,choices.includes(task.id)?choices.filter(id=>id!==task.id):[...choices,task.id]);
  };
  const submit=async(plan:any)=>{
    setBusy(true);
    try{await api.submit(plan.id,plan.draft.revision);const next=await api.state(plan.id);setStates(current=>({...current,[plan.id]:next}));message.success('本学期周期的志愿已提交，等待管理员审核');}
    catch(e){message.error(e instanceof Error?e.message:'提交失败，请刷新核对');}finally{setBusy(false);}
  };
  const periodTitle=(plan:any)=><Space wrap><Typography.Text strong>{plan.major||'未注明专业'} · {plan.cohort?`${plan.cohort}级 · `:''}{plan.academic_term===1?'第一':'第二'}学期</Typography.Text><Tag color={editable(plan)?'green':'default'}>{statusNames[plan.state]||plan.state}{plan.state==='open'&&!editable(plan)?'（已截止）':''}</Tag></Space>;
  const pool=currentPlans.map(plan=><Card key={plan.id} title={periodTitle(plan)} extra={<Tag>个人草稿 {plan.draft.task_ids.length}/5</Tag>}>
    <Typography.Paragraph type="secondary">{plan.name} · 截止 {dayjs(plan.deadline).format('YYYY-MM-DD HH:mm')} · 点击课程查看详情并预选</Typography.Paragraph>
    <StageSelectionTable plan={plan} tasks={plan.tasks} selected={plan.draft.task_ids} disabled={busy||!editable(plan)} onToggle={task=>void toggle(plan,task)} onTask={(task,week)=>setDetail({planId:plan.id,task,week})}/>
  </Card>);
  const basket=currentPlans.map(plan=><Card key={plan.id} title={periodTitle(plan)} extra={<Tag>草稿版本 {plan.draft.revision}</Tag>}>
    {plan.draft.task_ids.length?plan.draft.task_ids.map((taskId:number,index:number)=>{
      const task=plan.tasks.find((t:any)=>t.id===taskId);
      const move=(step:number)=>{const next=[...plan.draft.task_ids];[next[index],next[index+step]]=[next[index+step],next[index]];void save(plan,next);};
      return <div key={taskId} style={{display:'flex',gap:10,alignItems:'center',justifyContent:'space-between',padding:'12px 0',borderBottom:'1px solid #eee',flexWrap:'wrap'}}>
        <Space wrap><Tag color="purple">志愿 {index+1}</Tag><Typography.Text strong>{task?.name||`任务${taskId}`}</Typography.Text><Typography.Text type="secondary">{task?.group} · W{task?.start_week}—W{task?.end_week}</Typography.Text></Space>
        <Space><Button aria-label={`上移 ${plan.id} 志愿${index+1}`} icon={<ArrowUpOutlined/>} disabled={busy||!editable(plan)||index===0} onClick={()=>move(-1)}/><Button aria-label={`下移 ${plan.id} 志愿${index+1}`} icon={<ArrowDownOutlined/>} disabled={busy||!editable(plan)||index===plan.draft.task_ids.length-1} onClick={()=>move(1)}/><Button disabled={busy||!editable(plan)} onClick={()=>void save(plan,plan.draft.task_ids.filter((id:number)=>id!==taskId))}>移除</Button></Space>
      </div>;
    }):<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未预选课程，点击阶段课表中的课程加入"/>}
    <Space wrap style={{marginTop:16}}><Button type="primary" loading={busy} disabled={!editable(plan)||!plan.draft.task_ids.length} onClick={()=>Modal.confirm({title:'提交本学期周期的志愿？',content:`${plan.major||''} · ${plan.name}。本周期至少${Math.min(3,plan.tasks.length)}项、最多5项；与其他专业周期的草稿分别保存提交。`,okText:'确认提交',cancelText:'继续检查',onOk:()=>submit(plan)})}>提交本学期周期志愿</Button><Typography.Text type="secondary">最近提交：{plan.submission?`已提交${plan.submission.task_ids.length}项（记录${plan.submission.id}）`:'尚未提交'}</Typography.Text></Space>
  </Card>);
  const resultRows=currentPlans.flatMap(plan=>(plan.match?.candidates||[]).filter((c:any)=>c.teacher_id===user?.teacher_id).map((c:any)=>({...c,key:`${plan.id}-${c.task_id}`,plan_name:plan.name,task_name:plan.tasks.find((t:any)=>t.id===c.task_id)?.name})));
  const mine=currentPlans.flatMap(plan=>plan.tasks.filter((t:any)=>t.teacher_ids.includes(user?.teacher_id)).map((t:any)=>({...t,plan_name:plan.name,major:plan.major,phase:statusNames[plan.state]})));
  const activePlan=detail?states[detail.planId]:undefined;
  if(!teaching)return <Result status="403" title="账号没有选课职能"/>;
  if(ready===false)return <Navigate to="/profile" replace/>;
  if(loading)return <Spin/>;
  return <Space orientation="vertical" style={{width:'100%'}} size="large">
    <Space wrap style={{width:'100%',justifyContent:'space-between'}}><div><Typography.Title level={3} style={{marginBottom:4}}>教师选课与教学任务</Typography.Title><Typography.Text type="secondary">按学年浏览 · 跨专业选课 · 按学期周期分别提交</Typography.Text></div><Space wrap><Link to="/profile"><Button>维护个人资料</Button></Link>{(can(user,'admin')||can(user,'review')||can(user,'publish'))&&<Link to="/planning/review"><Button>管理与审核工作台</Button></Link>}<ProfessionalExport/></Space></Space>
    <Card><Space wrap><label>学年 <Select disabled={busy} aria-label="选课学年" value={year||undefined} style={{minWidth:170}} options={years.map(y=>({value:y,label:`${y}学年`}))} onChange={value=>{setYear(value);setMajor('all');setDetail(undefined);}}/></label><label>学期 <Select disabled={busy} aria-label="选课学期" value={term} style={{minWidth:150}} options={[{value:'all',label:'全部学期'},{value:'1',label:'第一学期'},{value:'2',label:'第二学期'}]} onChange={setTerm}/></label><label>专业 <Select disabled={busy} aria-label="选课专业" value={major} style={{minWidth:190}} options={[{value:'all',label:'全部专业（可跨专业选课）'},...majors.map(m=>({value:m,label:m}))]} onChange={setMajor}/></label><Button disabled={busy} onClick={()=>{void bootstrap();setRefresh(value=>value+1);}}>刷新周期</Button></Space>
      <Typography.Paragraph type="secondary" style={{marginTop:14,marginBottom:0}}>课程取自生效培养方案和管理员配置后开放的教学任务。阶段、时段与地点由学院预设。切换筛选不清空草稿；各专业、年级的学期周期独立保存提交，每周期最多5项意愿。</Typography.Paragraph></Card>
    {error&&<Alert showIcon type="error" title={error}/>}
    {gridLoading?<Spin/>:!currentPlans.length?<Empty description="所选学年、学期和专业暂无已开放的课程周期，请等待管理员生成并开放"/>:<Tabs activeKey={tab} onChange={setTab} items={[
      {key:'pool',label:'阶段课表选课',children:<Space orientation="vertical" style={{width:'100%'}} size="large">{pool}</Space>},
      {key:'draft',label:'我的志愿草稿与提交',children:<Space orientation="vertical" style={{width:'100%'}} size="large">{basket}</Space>},
      {key:'match',label:'我的匹配结果',children:<Table rowKey="key" dataSource={resultRows} pagination={{pageSize:10}} scroll={{x:850}} columns={[{title:'课程',dataIndex:'task_name'},{title:'周期',dataIndex:'plan_name'},{title:'专业匹配度',render:(_,r:any)=>r.professional_fit==null?'资料不足':`${r.professional_fit}%`},{title:'擅长课程',render:(_,r:any)=>r.skilled_course_match?'命中':'未命中'},{title:'综合分 / 105',render:(_,r:any)=>r.raw_total??'未知'},{title:'说明',dataIndex:'explanation'}]}/>},
      {key:'mine',label:'我的授课任务',children:<Table rowKey="id" dataSource={mine} pagination={{pageSize:10}} scroll={{x:800}} columns={[{title:'课程',dataIndex:'name'},{title:'专业',dataIndex:'major'},{title:'班级',dataIndex:'group'},{title:'阶段',render:(_,t:any)=>`W${t.start_week}—W${t.end_week}`},{title:'时段',render:(_,t:any)=>selectionSlots(t)},{title:'地点',dataIndex:'room_name'},{title:'状态',dataIndex:'phase'}]}/>},
    ]}/>}
    <Drawer title="课程详情与预选" open={Boolean(detail)} onClose={()=>setDetail(undefined)} width={520}>
      {detail&&activePlan&&<Space orientation="vertical" size="large" style={{width:'100%'}}>
        <Typography.Title level={4}>{detail.task.name}</Typography.Title>
        <Descriptions column={1} bordered items={[
          {key:'major',label:'专业 / 年级',children:`${activePlan.major||'未注明专业'} / ${activePlan.cohort||'未注明年级'}`},{key:'group',label:'教学组',children:detail.task.group},
          {key:'hours',label:'学分 / 学时',children:`${detail.task.credits}学分 / ${detail.task.required_hours}学时`},{key:'stage',label:'授课周段',children:`W${detail.task.start_week}—W${detail.task.end_week}`},
          {key:'slots',label:'上课时段',children:selectionSlots(detail.task)},{key:'room',label:'地点',children:detail.task.room_name||'待落实'},
          {key:'teachers',label:'任课教师',children:detail.task.teacher_names?.join('、')||'待管理员审核分配'},
          {key:'tags',label:'专业方向 / 领域',children:`${detail.task.direction||'待核对'} / ${(detail.task.tags||[]).join('、')||'待核对'}`},
          {key:'source',label:'课程来源',children:detail.task.source?.document_id?`培养方案修订${detail.task.source.revision}，原表${detail.task.source.course_metadata?.source_table??''}行${detail.task.source.course_metadata?.source_row??''}`:'管理员配置任务'},
        ]}/>
        <Alert type="info" showIcon title="预选仅表达授课意愿，不占据教师名额" description="选课后请在草稿页调整顺序并提交。教师自填资料和擅长课程将提供给系统匹配及管理员审核。"/>
        <Button type="primary" block loading={busy} disabled={!editable(activePlan)} onClick={()=>void toggle(activePlan,detail.task)}>{activePlan.draft.task_ids.includes(detail.task.id)?'取消本项预选':'预选此课程'}</Button>
        {!editable(activePlan)&&<Typography.Text type="secondary">该周期已截止或进入匹配发布阶段，当前仅供查看。</Typography.Text>}
        <Button block onClick={()=>{setDetail(undefined);setTab('draft');}}>查看志愿草稿</Button>
      </Space>}
    </Drawer>
  </Space>;
}
