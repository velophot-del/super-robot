import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Descriptions, Drawer, Empty, Modal, Result, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { Link, Navigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Input } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { gradeLabel, normalizeCohort, stageClassScope } from '../lib/adminStageGrid';
import { planningApi as api } from '../api/planning';
import { intelligenceApi } from '../api/client';
import { openSelectionPlans } from '../lib/teacherWorkbench';
import { academicYear,filterSelectionPlans,selectionSlots } from '../lib/selectionGrid';
import StageSelectionTable from '../components/StageSelectionTable';
import WorkloadEstimatePanel from '../components/WorkloadEstimatePanel';
import ConfirmedWorkloadPanel from '../components/ConfirmedWorkloadPanel';
import HelpTip from '../components/HelpTip';
import ProfessionalExport from '../components/ProfessionalExport';

const statusNames:Record<string,string>={open:'开放选课',matched:'匹配审核中',published:'已发布'};
const editable=(p:any)=>(p.state==='open'&&new Date(p.deadline).getTime()>Date.now())||p.can_resubmit;

export default function TeacherSelectionPage(){
  const {user}=useAuth();
  const [plans,setPlans]=useState<any[]>([]),[allPlans,setAllPlans]=useState<any[]>([]),[states,setStates]=useState<Record<number,any>>({});
  const [year,setYear]=useState(''),[term,setTerm]=useState('all'),[major,setMajor]=useState('all');
  const [cohort,setCohort]=useState('all'),[search,setSearch]=useState('');
  const [ready,setReady]=useState<boolean>(),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [detail,setDetail]=useState<{planId:number;task:any;week:number}>();
  const [recommend,setRecommend]=useState<any>();
  const [qaQ,setQaQ]=useState(''), [qaA,setQaA]=useState(''), [qaBusy,setQaBusy]=useState(false);
  const teaching=can(user,'teaching');
  const [now,setNow]=useState(Date.now());
  // 只在最近一个填报截止时间唤醒，避免整页每秒重渲染。
  useEffect(()=>{
    const deadlines=plans.map((p:any)=>new Date(p.deadline).getTime()).filter(t=>Number.isFinite(t)&&t>Date.now());
    if(!deadlines.length)return;
    const delay=Math.min(Math.max(Math.min(...deadlines)-Date.now()+1000,1000),2_147_483_647);
    const timer=setTimeout(()=>setNow(Date.now()),delay);
    return()=>clearTimeout(timer);
  },[plans,now]);
  const bootstrap=useCallback(async()=>{
    if(!teaching)return;setLoading(true);setError('');
    try{
      const personal=await api.selfProfile();setReady(personal.ready);if(!personal.ready)return;
      const all=await api.plans();setAllPlans(all);
      const list=openSelectionPlans<any>(all);setPlans(list);
      setYear(current=>list.some((p:any)=>(p.academic_year||academicYear(p.start_date))===current)?current:
        (()=>{const first=list.find(editable)||list[0];return first?(first.academic_year||academicYear(first.start_date)):'';})());
    }catch(e){setError(e instanceof Error?e.message:'读取选课信息失败');}finally{setLoading(false);}
  },[teaching]);
  useEffect(()=>{void bootstrap();},[bootstrap]);
  useEffect(()=>{
    if(!teaching)return;
    const list=openSelectionPlans<any>(allPlans);
    const target=list.find(editable)||list[0];
    if(!target){setRecommend(undefined);return;}
    intelligenceApi.recommend(target.id).then(setRecommend).catch(()=>setRecommend(undefined));
  },[allPlans,teaching]);
  const askMyQa=async()=>{
    if(!qaQ.trim())return;
    setQaBusy(true);
    try{const result:any=await intelligenceApi.myQa(qaQ.trim());setQaA(result.answer||'');}
    catch(e){message.error(e instanceof Error?e.message:'问答失败');}
    finally{setQaBusy(false);}
  };
  const filtered=useMemo(()=>filterSelectionPlans(openSelectionPlans(plans,now),year,term,major),[plans,now,year,term,major]);
  // 选课阶段只显示按 25 人基数计算的预估课时；全部开放周期结束后再显示真实工作量。
  const selectionActive=plans.some((p:any)=>p.state==='open'&&new Date(p.deadline).getTime()>now);
  const ids=filtered.map(p=>p.id).join(',');
  const [gridLoading,setGridLoading]=useState(false),[refresh,setRefresh]=useState(0);
  const gridScope=useRef('');
  useEffect(()=>{
    const reload=()=>{if(!busy&&document.visibilityState==='visible')setRefresh(v=>v+1);};
    const timer=setInterval(reload,30000);window.addEventListener('focus',reload);
    return()=>{clearInterval(timer);window.removeEventListener('focus',reload);};
  },[busy]);
  useEffect(()=>{
    let active=true;const numbers=ids?ids.split(',').map(Number):[];
    const scopeChanged=gridScope.current!==ids;
    gridScope.current=ids;
    if(scopeChanged){setStates({});setDetail(undefined);}
    if(!numbers.length){setGridLoading(false);return()=>{active=false;};}
    setGridLoading(scopeChanged);setError('');
    void Promise.allSettled(numbers.map(id=>api.state(id))).then(results=>{
      if(!active)return;const loaded:Record<number,any>={};let failed=0;
      results.forEach((r,i)=>{if(r.status==='fulfilled')loaded[numbers[i]]=r.value;else failed++;});
      setStates(loaded);setDetail(current=>{if(!current)return current;const task=loaded[current.planId]?.tasks.find((t:any)=>t.id===current.task.id);return task?{...current,task}:undefined;});if(failed)setError(`${failed}个周期读取失败，请点击刷新重试；未加载的课程不会被提交。`);setGridLoading(false);
    });return()=>{active=false;};
  },[ids,refresh]);
  const currentPlans=openSelectionPlans<any>(filtered.map(p=>states[p.id]).filter(Boolean),now);
  const years=[...new Set(plans.map(p=>p.academic_year||academicYear(p.start_date)))].sort().reverse();
  const majors=[...new Set(plans.filter(p=>(p.academic_year||academicYear(p.start_date))===year).flatMap(p=>{
    const fromPlan=p.major?[p.major]:[];
    const fromTasks=(states[p.id]?.tasks||[]).map((t:any)=>t.major||t.department||t.source?.major).filter(Boolean);
    return [...fromPlan,...fromTasks,...(states[p.id]?.class_scopes||[]).map((c:any)=>c.department).filter(Boolean)];
  }))].sort();
  const save=async(plan:any,taskIds:number[])=>{
    setBusy(true);
    try{const draft=await api.saveDraft(plan.id,{revision:plan.draft.revision,plan_revision:plan.revision,task_ids:taskIds});setStates(current=>({...current,[plan.id]:{...plan,draft}}));message.success('已保存个人草稿');}
    catch(e){message.error(e instanceof Error?e.message:'保存失败，请刷新后核对');}finally{setBusy(false);}
  };
  const toggle=async(plan:any,task:any)=>{
    const choices:number[]=plan.draft.task_ids;
    if(!choices.includes(task.id)&&choices.length>=5){message.warning('每个周期最多选择5门课程');return;}
    await save(plan,choices.includes(task.id)?choices.filter(id=>id!==task.id):[...choices,task.id]);
  };
  const submit=async(plan:any)=>{
    setBusy(true);
    try{await api.submit(plan.id,plan.draft.revision);const next=await api.state(plan.id);setStates(current=>({...current,[plan.id]:next}));message.success('本学期周期的选课已提交，等待管理员审核');}
    catch(e){message.error(e instanceof Error?e.message:'提交失败，请刷新核对');}finally{setBusy(false);}
  };
  const periodTitle=(plan:any)=><Space wrap><Typography.Text strong>{plan.global_cycle?'全学院 · 所有年级与专业':`${plan.major||'未注明专业'}${plan.cohort?` · ${gradeLabel(plan.cohort)}`:''}`} · {plan.academic_term===1?'第一':'第二'}学期</Typography.Text><Tag color={editable(plan)?'green':'default'}>{statusNames[plan.state]||plan.state}{plan.state==='open'&&!editable(plan)?'（已截止）':''}</Tag></Space>;
  const basket=(plan:any)=><div>
    {(plan.submission?.reviews||[]).filter((r:any)=>r.status==='returned').map((r:any)=><Alert key={r.task_id} type="warning" showIcon title={`${plan.tasks.find((t:any)=>t.id===r.task_id)?.name||'课程申请'}已退回`} description={r.reason} style={{marginBottom:8}}/>)}
    <Typography.Title level={5}>已选课程</Typography.Title>
    {plan.draft.task_ids.length?plan.draft.task_ids.map((taskId:number)=>{
      const task=plan.tasks.find((t:any)=>t.id===taskId);
      return <div key={taskId} style={{display:'flex',gap:10,alignItems:'center',justifyContent:'space-between',padding:'12px 0',borderBottom:'1px solid #eee',flexWrap:'wrap'}}>
        <Space wrap><Typography.Text strong>{task?.name||`任务${taskId}`}</Typography.Text><Typography.Text type="secondary">{task?.group} · W{task?.start_week}—W{task?.end_week}</Typography.Text></Space>
        <Button disabled={busy||!editable(plan)} onClick={()=>void save(plan,plan.draft.task_ids.filter((id:number)=>id!==taskId))}>移除</Button>
      </div>;
    }):<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未预选课程，点击阶段课表中的课程加入"/>}
    <Space wrap style={{marginTop:16}}><Button loading={busy} disabled={!editable(plan)} onClick={()=>void save(plan,plan.draft.task_ids)}>保存</Button><Button type="primary" loading={busy} disabled={!editable(plan)||!plan.draft.task_ids.length} onClick={()=>Modal.confirm({title:'提交本学期周期的选课？',content:`${plan.global_cycle?'全学院':plan.major||''} · ${plan.name}。本周期至少${Math.min(3,plan.tasks.length)}门、最多5门；与其他周期的草稿分别保存提交。`,okText:'确认提交',cancelText:'继续检查',onOk:()=>submit(plan)})}>提交</Button><Typography.Text type="secondary">最近提交：{plan.submission?`已提交${plan.submission.task_ids.length}项（记录${plan.submission.id}）`:'尚未提交'}</Typography.Text></Space>
  </div>;
  const cohorts=[...new Set<string>(Object.values(states).flatMap((p:any)=>[...(p.tasks||[]).map((t:any)=>normalizeCohort(t.cohort||p.cohort)),...(p.class_scopes||[]).map((c:any)=>normalizeCohort(c.grade))]).filter(Boolean))].sort().reverse();
  const visibleTasks=(plan:any)=>plan.tasks.filter((t:any)=>(major==='all'||(t.major||t.department||t.source?.major)===major)
    &&(cohort==='all'||normalizeCohort(t.cohort||plan.cohort)===cohort)
    &&(!search||[t.name,t.group,t.room_name,...(t.teacher_names||[])].filter(Boolean).join(' ').toLowerCase().includes(search.toLowerCase())));
  const gridPlan=(plan:any)=>({...plan,groups:(plan.groups||[...new Set(plan.tasks.map((t:any)=>t.group))]).filter((group:string)=>{
    const scope=stageClassScope(group,plan.class_scopes||[],plan.tasks);
    return (major==='all'||scope.major===major)&&(cohort==='all'||scope.cohort===cohort)
      &&(!search||group.includes(search)||visibleTasks(plan).some((t:any)=>t.group===group));
  })});
  const pool=currentPlans.map(plan=><section key={plan.id} className="selection-cycle"><div className="selection-header">{periodTitle(plan)}<Tag>个人草稿 {plan.draft.task_ids.length}/5 · 修订 {plan.revision}</Tag></div>
    <Typography.Paragraph type="secondary">{plan.name} · 截止 {dayjs(plan.deadline).format('YYYY-MM-DD HH:mm')} · 点击课程查看详情并预选</Typography.Paragraph>
    <StageSelectionTable plan={gridPlan(plan)} tasks={visibleTasks(plan)} selected={plan.draft.task_ids} disabled={busy||!editable(plan)} onToggle={task=>void toggle(plan,task)} onTask={(task,week)=>setDetail({planId:plan.id,task,week})}/>
    <WorkloadEstimatePanel key={plan.id} plan={plan} disabled={busy||!editable(plan)}/>
    {basket(plan)}
  </section>);
  const activePlan=detail?states[detail.planId]:undefined;
  if(!teaching)return <Result status="403" title="账号没有选课职能"/>;
  if(ready===false)return <Navigate to="/profile" replace/>;
  if(loading)return <Spin/>;
  return <div className="selection-workspace">
    <Space wrap style={{width:'100%',justifyContent:'space-between'}}><div><Typography.Title level={3} style={{marginBottom:4}}>选课工作台</Typography.Title><Typography.Text type="secondary">仅显示当前开放周期 · 跨专业选课 · 保存后提交</Typography.Text></div><Space wrap><Link to="/profile"><Button>维护个人资料</Button></Link>{(can(user,'admin')||can(user,'review')||can(user,'publish'))&&<Link to="/planning/review"><Button>管理与审核工作台</Button></Link>}<ProfessionalExport/></Space></Space>
    <div className="selection-filters"><HelpTip title="课程取自课程管理中的活动课程库，并由管理员配置后开放为教学任务。阶段、时段与地点由学院统一安排。勾选会自动保存，也可点击“保存”再次确认；切换筛选不清空草稿；各周期独立保存提交，每周期最多选择5门课程。"/><Space wrap><label>学年 <Select disabled={busy} aria-label="选课学年" value={year||undefined} style={{minWidth:170}} options={years.map(y=>({value:y,label:`${y}学年`}))} onChange={value=>{setYear(value);setMajor('all');setDetail(undefined);}}/></label><label>学期 <Select disabled={busy} aria-label="选课学期" value={term} style={{minWidth:150}} options={[{value:'all',label:'全部学期'},{value:'1',label:'第一学期'},{value:'2',label:'第二学期'}]} onChange={setTerm}/></label><label>专业 <Select disabled={busy} aria-label="选课专业" value={major} style={{minWidth:190}} options={[{value:'all',label:'全部专业（可跨专业选课）'},...majors.map(m=>({value:m,label:m}))]} onChange={setMajor}/></label><label>年级 <Select aria-label="选课年级" value={cohort} onChange={setCohort} style={{minWidth:140}} options={[{value:'all',label:'全部年级'},...cohorts.map(value=>({value,label:gradeLabel(value)}))]}/></label><Input aria-label="搜索课程教师班级地点" prefix={<SearchOutlined/>} placeholder="搜索课程、教师、班级或地点" value={search} onChange={e=>setSearch(e.target.value)} style={{width:260}} allowClear/><Button icon={<ReloadOutlined/>} disabled={busy} onClick={()=>{void bootstrap();setRefresh(value=>value+1);}}>刷新</Button></Space></div>
    <div className="selection-summary"><div><strong>{currentPlans.length}</strong><span>开放周期</span></div><div><strong>{currentPlans.reduce((sum,p)=>sum+visibleTasks(p).length,0)}</strong><span>课程任务</span></div><div><strong>{new Set(currentPlans.flatMap(p=>visibleTasks(p).map((t:any)=>t.group))).size}</strong><span>开课班级</span></div><div><strong>{currentPlans.reduce((sum,p)=>sum+p.draft.task_ids.length,0)}</strong><span>已选任务</span></div></div>
    {recommend?.recommendations?.length>0&&<Card size="small" title="智能推荐" extra={<Tag color="purple">基于您的画像</Tag>} style={{marginBottom:12}}>
      <Typography.Paragraph type="secondary" style={{marginBottom:8}}>{recommend.summary}</Typography.Paragraph>
      <Space direction="vertical" size="small" style={{width:'100%'}}>
        {recommend.recommendations.map((r:any)=><div key={r.task_id} style={{display:'flex',justifyContent:'space-between',alignItems:'center',gap:12,flexWrap:'wrap'}}>
          <Space wrap><Typography.Text strong>{r.name}</Typography.Text><Typography.Text type="secondary">{r.group}{r.direction?` · ${r.direction}`:''}</Typography.Text></Space>
          <Tag color="blue">{r.reason}</Tag>
        </div>)}
      </Space>
    </Card>}
    <Card size="small" title="智能助手" extra={<Tag color="green">AI 问答</Tag>} style={{marginBottom:12}}>
      <Space.Compact style={{width:'100%'}}>
        <Input aria-label="智能助手输入" placeholder="问我选课、推荐或我的画像，如「我该选哪几门课？」" value={qaQ} onChange={e=>setQaQ(e.target.value)} onPressEnter={()=>void askMyQa()}/>
        <Button type="primary" loading={qaBusy} onClick={()=>void askMyQa()}>提问</Button>
      </Space.Compact>
      {qaA&&<Alert style={{marginTop:8}} type="info" showIcon message={qaA}/>}
    </Card>
    {error&&<Alert showIcon type="error" title={error}/>}
    {gridLoading?<Spin/>:!currentPlans.length?<Empty description="暂无符合筛选条件的开放选课周期，请等待管理员开放"/>:<Space orientation="vertical" style={{width:'100%'}} size="large">{pool}</Space>}
    {!selectionActive&&<ConfirmedWorkloadPanel plans={allPlans} refreshKey={refresh}/>}
    <Drawer title="课程详情与预选" open={Boolean(detail)} onClose={()=>setDetail(undefined)} width={520}>
      {detail&&activePlan&&<Space orientation="vertical" size="large" style={{width:'100%'}}>
        <Typography.Title level={4}>{detail.task.name}</Typography.Title>
        <Descriptions column={1} bordered items={[
          {key:'major',label:'专业 / 年级',children:`${detail.task.major||detail.task.department||activePlan.major||'未注明专业'} / ${gradeLabel(detail.task.cohort||activePlan.cohort)||'未注明年级'}`},{key:'group',label:'教学组',children:detail.task.group},
          {key:'hours',label:'学分 / 学时',children:`${detail.task.credits}学分 / ${detail.task.required_hours}学时`},{key:'stage',label:'授课周段',children:`W${detail.task.start_week}—W${detail.task.end_week}`},
          {key:'slots',label:'上课时段',children:selectionSlots(detail.task,detail.task.start_week)||'待统一安排'},{key:'room',label:'地点',children:detail.task.room_name||'待落实'},
          {key:'teachers',label:'任课教师',children:detail.task.teacher_names?.join('、')||'待管理员审核分配'},
          {key:'tags',label:'专业方向 / 领域',children:`${detail.task.direction||'待核对'} / ${(detail.task.tags||[]).join('、')||'待核对'}`},
          {key:'source',label:'课程来源',children:detail.task.source?.course_id?`课程库 · ${detail.task.source.major||'通用课程'} · ${detail.task.source.cohort||'不限年级'}级`:detail.task.source?.document_id?`历史培养方案修订${detail.task.source.revision}`:'管理员配置任务'},
        ]}/>
        <Alert type="info" showIcon title="预选仅表达授课意愿，不占据教师名额" description="选课后请在本页阶段课表下方核对已选课程并提交。教师自填资料和擅长课程将提供给系统匹配及管理员审核。"/>
        <Button type="primary" block loading={busy} disabled={!editable(activePlan)} onClick={()=>void toggle(activePlan,detail.task)}>{activePlan.draft.task_ids.includes(detail.task.id)?'取消本项预选':'预选此课程'}</Button>
        {!editable(activePlan)&&<Typography.Text type="secondary">该周期已截止或进入匹配发布阶段，当前仅供查看。</Typography.Text>}
        <Button block onClick={()=>{setDetail(undefined);}}>返回选课工作台</Button>
      </Space>}
    </Drawer>
  </div>;
}
