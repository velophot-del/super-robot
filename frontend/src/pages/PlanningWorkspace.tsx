import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Col, DatePicker, Descriptions, Empty, Form, Input, InputNumber, message,
  Modal, Row, Select, Space, Spin, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import { DeleteOutlined, InfoCircleOutlined, PlusOutlined, RobotOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi as api } from '../api/planning';
import { classApi, classroomApi, intelligenceApi } from '../api/client';
import ProfessionalExport from '../components/ProfessionalExport';
import TeacherSelectionPage from './TeacherSelectionPage';
import { taskLimitsPayload, taskCourseInfo } from '../lib/taskForm';
import { gradeLabel } from '../lib/adminStageGrid';
import { academicCalendar, suggestedMonday } from '../lib/academicCalendar';
import AdminStagePlanner from '../components/AdminStagePlanner';
import ReviewTimetable from '../components/ReviewTimetable';
import MatchWeightsPanel from '../components/MatchWeightsPanel';
import DepartmentAiReviewPanel from '../components/DepartmentAiReviewPanel';
import {departmentDirectAssign, departmentScheduleDraft} from '../lib/departmentSchedule';
import DepartmentScheduleInbox from '../components/DepartmentScheduleInbox';

const { Title, Text, Paragraph } = Typography;
const stateNames: Record<string,string> = { draft:'计划草稿', open:'开放填报', matched:'匹配待审核', published:'已发布' };
const textList = (s: string | string[]) => Array.isArray(s) ? s : (s || '').split(/[,，\n]/).map(x => x.trim()).filter(Boolean);

async function loadAllClasses(){
  const rows:any[]=[];let skip=0;
  while(skip<10000){const page=await classApi.list({skip,limit:500}) as any[];rows.push(...page);if(page.length<500)break;skip+=page.length;}
  return rows;
}

export function ManagementPlanningWorkspace({section='plan'}:{section?:'plan'|'review'}={}) {
  const { user }=useAuth();
  const admin=can(user,'admin'), review=can(user,'review');
  const [plans,setPlans]=useState<any[]>([]), [id,setId]=useState<number>(), [loadedState,setState]=useState<any>();
  const state=loadedState||{state:'',draft:{revision:0,task_ids:[]},match:null,rule_confirmed:false};
  const [profiles,setProfiles]=useState<any[]>([]), [classes,setClasses]=useState<any[]>([]);
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [planInfoOpen,setPlanInfoOpen]=useState(false);
  const [modal,setModal]=useState<'plan'|'task'|'profile'|null>(null), [profileId,setProfileId]=useState<number>();
  const [editingTask,setEditingTask]=useState<any>();
  const [autoBuild,setAutoBuild]=useState<any>();
  const [matchExplain,setMatchExplain]=useState<any>();
  const [qaQ,setQaQ]=useState(''), [qaA,setQaA]=useState(''), [qaBusy,setQaBusy]=useState(false);
  const [rooms,setRooms]=useState<any[]>([]);
  const [roomsLoading,setRoomsLoading]=useState(false);
  const [form]=Form.useForm();
  const calendarStart=Form.useWatch('start_date',form);
  const calendarWeeks=Form.useWatch('weeks',form);
  const calendarRows=academicCalendar(calendarStart||'',calendarWeeks||20);
  useEffect(()=>{
    if(calendarStart)form.setFieldValue('term',dayjs(calendarStart).month()>=7||dayjs(calendarStart).month()===0?1:2);
  },[calendarStart,form]);
  const [reviewReason,setReviewReason]=useState('已核对专业领域和实际负荷');
  const [changeRequests,setChangeRequests]=useState<any[]>([]);
  const [reviewBatch,setReviewBatch]=useState<any>({plans:[],reviews:[]});
  const [departmentBoard,setDepartmentBoard]=useState<any>({plans:[]});

  const load = useCallback(async () => {
    setError('');
    try {
      const list=await api.plans();setPlans(list);
      const target=id ?? list[0]?.id;
      if(target) { if(!id)setId(target); const results=await Promise.all([
        api.state(target,section==='review'&&!admin),
        section==='review'?api.reviewOverview(target):Promise.resolve({plans:[],reviews:[]}),
        section==='review'&&!admin?api.departmentSchedule(target):Promise.resolve({plans:[]}),
      ]);setState(results[0]);setReviewBatch(results[1]);setDepartmentBoard(results[2]);
      } else {setState(undefined);setReviewBatch({plans:[],reviews:[]});setDepartmentBoard({plans:[]});}
      if(admin){ const [p,c]=await Promise.all([api.profiles(),loadAllClasses()]);setProfiles(p);setClasses(c); }
    }catch(e){setError(e instanceof Error?e.message:'加载失败');}finally{setLoading(false);}
  },[id,admin,section]);
  useEffect(()=>{void load();},[load]);
  useEffect(()=>{
    if(!admin||state?.state!=='published'||!id){setChangeRequests([]);return;}
    void api.changeRequests(id).then(setChangeRequests).catch(()=>setChangeRequests([]));
  },[admin,id,state?.state]);

  const action=async(fn:()=>Promise<unknown>)=>{
    setBusy(true);try{await fn();await load();message.success('已保存');}catch(e){message.error(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}
  };
  const aiMatch=async()=>{
    if(!id)return;
    setBusy(true);
    try{
      const result:any=await api.matchWithAi(id);
      await load();
      if(result.ai_applied)message.success(`AI 排序已落位 ${result.auto_assigned} 门课程`);
      else if(result.ai_used)message.warning(`AI 已排序，但候选未通过校验，已按规则落位 ${result.auto_assigned} 门`);
      else message.warning(`AI 未参与排序${result.ai_reason?`：${result.ai_reason}`:''}；已按规则落位 ${result.auto_assigned} 门`);
    }catch(e){message.error(e instanceof Error?e.message:'AI 匹配失败');}
    finally{setBusy(false);}
  };
  const openModal=(type:'plan'|'task'|'profile',p?:any)=>{
    form.resetFields();setModal(type);setProfileId(p?.id);
    setEditingTask(type==='task'?p:undefined);
    if(type==='plan')form.setFieldsValue({weeks:20,term:(dayjs().month()>=7||dayjs().month()===0)?1:2,rule_confirmed:false,groups:[]});
    if(type==='task'){
      setRoomsLoading(true);
      void classroomApi.list({limit:500}).then((data:any)=>setRooms(data)).catch(()=>message.error('教室列表加载失败，请重试')).finally(()=>setRoomsLoading(false));
    }
    if(type==='task'&&p)form.setFieldsValue({
      room_id:p.room_id??null,
      teacher_count:p.teacher_count??1,
      max_students:p.max_students??30,
      slots:p.slots||[],
    });
    if(type==='profile')form.setFieldsValue({...p,tags:(p.tags||[]).join('，'),team_codes:(p.team_codes||[]).join('，'),taught_codes:(p.taught_codes||[]).join('，'),external_hours:JSON.stringify(p.external_hours||{})});
  };
  const saveModal=async()=>{
    const v=await form.validateFields();
    setBusy(true);
    try{
      if(modal==='plan'){const p=await api.createPlan({...v,global_cycle:true,department_review:true,deadline:new Date(v.deadline).toISOString()});setId(p.id);}
      if(modal==='task'){
        if(!editingTask)throw new Error('请先从导入课程库拖入任务');
        await api.setTaskLimits(id!,editingTask.id,taskLimitsPayload(v,state.revision));
      }
      if(modal==='profile')await api.saveProfile(profileId!,{...v,tags:textList(v.tags),team_codes:textList(v.team_codes),taught_codes:textList(v.taught_codes),external_hours:JSON.parse(v.external_hours||'{}')});
      setModal(null);await load();message.success('已保存');
    }catch(e){message.error(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
  };
  const doAutoBuild=async(teacher:any)=>{
    setBusy(true);
    try{const result:any=await api.autoBuildProfile(teacher.id);setAutoBuild({teacher,result});}
    catch(e){message.error(e instanceof Error?e.message:'画像构建失败');}
    finally{setBusy(false);}
  };
  const confirmAutoBuild=async()=>{
    if(!autoBuild)return;const p=autoBuild.result.proposal;
    setBusy(true);
    try{
      await api.saveProfile(autoBuild.teacher.id,{direction:p.direction,tags:p.tags,team_codes:p.team_codes||[],taught_codes:p.taught_codes||[],verified:true,weekly_limit:20,course_limit:3,external_hours:{}});
      setAutoBuild(undefined);await load();message.success('画像已按建议写入');
    }catch(e){message.error(e instanceof Error?e.message:'写入失败');}finally{setBusy(false);}
  };
  const loadMatchExplanations=async()=>{
    if(!id)return;
    setBusy(true);
    try{const result:any=await api.matchExplanations(id);setMatchExplain(result);}
    catch(e){message.error(e instanceof Error?e.message:'解释生成失败');}
    finally{setBusy(false);}
  };
  const askQa=async()=>{
    if(!qaQ.trim())return;
    setQaBusy(true);
    try{const result:any=await intelligenceApi.qa(qaQ.trim());setQaA(result.answer||'');}
    catch(e){message.error(e instanceof Error?e.message:'问答失败');}
    finally{setQaBusy(false);}
  };
  const tasks:any[]=state?.tasks||[];
  const taskName=(taskId:number)=>tasks.find(t=>t.id===taskId)?.name||String(taskId);
  const reviewPlans:any[]=reviewBatch.plans||[];
  const reviewQueuePlanId=reviewPlans.find(p=>['open','matched'].includes(p.state))?.id;
  const batchTasks=reviewPlans.flatMap(p=>(p.tasks||[]).map((t:any)=>({...t,match_id:p.match?.id,plan_state:p.state,plan_name:p.name})));
  const batchMatch={candidates:reviewPlans.flatMap(p=>p.match?.candidates||[])};
  const directorTasks=(departmentBoard.plans||[]).flatMap((p:any)=>(p.tasks||[]).filter((task:any)=>task.can_edit_department_schedule).map((task:any)=>({...task,applicants:(task.applicants||[]).filter((applicant:any)=>applicant.selected),match_id:p.match?.id,plan_state:p.state})));
  const matchView=<Space orientation="vertical" size="large" style={{width:'100%'}}>
    {review&&id&&<DepartmentAiReviewPanel planId={id} admin={admin} version={reviewBatch} disabled={busy||!['open','matched'].includes(state.state)}/>}
    {admin&&review&&<Card size="small" title="主任调剂待确认">{reviewQueuePlanId?<DepartmentScheduleInbox planId={reviewQueuePlanId} disabled={busy} onRefresh={()=>void load()}/>:<Empty description="当前学年学期没有开放或匹配中的周期"/>}</Card>}
    {admin&&!state.department_review&&state.state!=='published'&&<Button onClick={()=>Modal.confirm({title:'启用两级审核',content:'现有申报将进入教研室初审，已有任课分配保留为待复核建议，需初审通过后重新匹配。',onOk:async()=>{await api.enableDepartmentReview(id!);await load();}})}>启用教研室初审</Button>}
    <Alert showIcon type="info" title={admin?'系统自动匹配 + 人工审核调剂':'教研室主任审核'} description={admin?`综合推荐按当前权重合计 ${state.match_weight_total??95} 分计算；专业适配度只使用方向和领域。可运行系统规则匹配，或使用「AI 排序并自动落位」让模型按同一套权重重排候选；落位前仍会校验教师意愿、回避与容量。管理员可在下方实时全学院课表中核对并人工调剂。`:'按本教研室范围审核教师选课，在课程卡片中通过或退回申请、调整任课教师；教师调整无需理由，提交管理员最终确认。'}/>
    {admin&&<Card size="small" title="匹配权重设置" style={{marginBottom:16}}>
      <MatchWeightsPanel plan={state} disabled={busy} onSaved={load}/>
    </Card>}
    {admin&&<Space wrap>
      {!state.rule_confirmed&&state.state!=='published'&&<Button onClick={()=>void action(()=>api.confirmMatchRules(id!))}>确认当前匹配规则</Button>}
      <Button type="primary" loading={busy} disabled={!state.rule_confirmed||!['open','matched'].includes(state.state)} onClick={()=>void action(()=>api.match(id!))}>运行系统匹配（自动落位） / 保留锁定重跑</Button>
      <Button icon={<RobotOutlined/>} loading={busy} disabled={!state.rule_confirmed||!['open','matched'].includes(state.state)} onClick={()=>void aiMatch()}>AI 排序并自动落位</Button>
      <Text>已提交教师：{state.submission_count??'—'}</Text>
      {state.match&&<Button loading={busy} onClick={()=>void loadMatchExplanations()}>AI 解释匹配理由</Button>}
      {state.match?.ai?.used&&<Tag color="purple">AI 排序{state.match.ai.applied?` · 落位${state.match.ai.applied}门`:' · 未采用'}</Tag>}
    </Space>}
    {admin&&!state.rule_confirmed&&<Alert type="warning" showIcon title="请先确认当前匹配规则，再运行自动匹配"/>}
    {admin&&<Space wrap>{reviewPlans.filter(p=>p.id!==id).map(p=><Button key={p.id} disabled={busy||!p.rule_confirmed} onClick={()=>void action(()=>api.match(p.id))}>匹配：{p.name}{!p.rule_confirmed?'（规则待确认）':''}</Button>)}</Space>}
    {state.match?<Table rowKey={r=>`${r.task_id}-${r.teacher_id}`} dataSource={state.match.candidates} pagination={false} scroll={{x:760}}
      columns={[
        {title:'课程任务',render:(_,r:any)=>`${taskName(r.task_id)} · ${tasks.find(t=>t.id===r.task_id)?.group}`},
        {title:'教师',render:(_,r:any)=>r.teacher_name},
        {title:'专业适配度',render:(_,r:any)=>r.professional_fit==null?<Tag color="orange">资料待核实</Tag>:`${r.professional_fit}%`},
        {title:'综合推荐',render:(_,r:any)=>r.raw_total==null?'待核实':`${r.raw_total}/${r.maximum??state.match?.maximum??state.match_weight_total??95} (${r.normalized_total}%)`},
        {title:'硬约束',render:(_,r:any)=>r.eligible?<Tag color="green">可审核</Tag>:<Text type="danger">{r.reasons.join('；')}</Text>},
      ]} expandable={{expandedRowRender:(r:any)=><Space direction="vertical" size="small" style={{width:'100%'}}>
        {r.explanation&&<Text type="secondary">{r.explanation}</Text>}
        <Space wrap>{r.components.map((c:any)=><Tag key={c.name}>{c.name}：{c.score??'未知'}/{c.maximum}{c.hits?.length?` · 命中${c.hits.join('、')}`:''}</Tag>)}</Space>
      </Space>}}/>:admin?<Empty description="尚未运行匹配"/>:null}
    {review&&<Card title={admin?"全学院实时课表与人工调剂":"本教研室实时课表与教师审核"}>
      {admin&&<Space wrap style={{marginBottom:12,width:'100%'}}>
        <Text strong>调剂说明</Text>
        <Input aria-label="调剂说明" value={reviewReason} onChange={e=>setReviewReason(e.target.value)} placeholder="审核依据与改选原因" style={{minWidth:320,flex:1}}/>
      </Space>}
      <ReviewTimetable plan={state} tasks={admin?(state.state==='published'?tasks:batchTasks):directorTasks} match={state.state==='published'?state.match:batchMatch} busy={busy} admin={admin}
        canAssign={state.state!=='published'&&(admin?reviewPlans.some(p=>['open','matched'].includes(p.state)):true)} reason={reviewReason} onReviewed={()=>void load()}
        onRoom={(task,roomId)=>void action(()=>api.setTaskRoom(task.plan_id||id!,task.id,roomId))}
        onAssign={(task,teacher_ids)=>void action(async()=>{
          const planId=task.plan_id||id!;
          if(admin){
            await api.reassign(planId,task.id,{teacher_ids,base_revision:task.base_revision,base_fingerprint:task.base_fingerprint,reason:reviewReason});
          }else if(departmentDirectAssign(task)){
            await api.reassign(planId,task.id,{teacher_ids,base_revision:task.base_revision,base_fingerprint:task.base_fingerprint});
          }else{
            const draft:any=await api.saveDepartmentScheduleDraft(planId,task.id,{...departmentScheduleDraft(task),base_revision:task.base_revision,base_fingerprint:task.base_fingerprint,teacher_ids,reason:''});
            await api.submitDepartmentSchedule(planId,task.id,draft.proposal_id);
          }
        })}/>
    </Card>}

  </Space>;

  const tabs:any[]=[];
  if(admin)tabs.push({key:'pool',label:'课程表编排',children:<AdminStagePlanner key={state.id} plan={state} classes={classes} onChange={load} onEdit={task=>openModal('task',task)}/>});
  tabs.push({key:'match',label:review?'匹配与审核':'我的匹配结果',children:matchView});
  if(admin)tabs.push({key:'profiles',label:'教师专业画像',children:<Table rowKey="id" dataSource={profiles} pagination={false} columns={[{title:'教师',dataIndex:'name'},{title:'方向',dataIndex:'direction'},{title:'领域',render:(_,p:any)=>p.tags.join('、')},{title:'资料来源',render:(_,p:any)=>p.professional_profile_source==='self_declared'?'教师自填':'管理员登记'},{title:'管理记录核实',render:(_,p:any)=>p.verified?'已核对':'待核对'},{title:'操作',render:(_,p:any)=><Space><Button onClick={()=>openModal('profile',p)}>维护画像 / 外部课时</Button><Button loading={busy} onClick={()=>void doAutoBuild(p)}>自动构建画像</Button></Space>}]}/>});

  return <div>
    <Title level={3}>{section==='plan'?'排课周期计划':!admin&&user?.grants?.some(g=>g.capability==='lead')?'教研室主任审核':'匹配与审核'}</Title>
    <Paragraph>教师先选课并提交意愿，系统提供专业匹配依据，审核确认后分配。每教学组同周最多2门、同日1门。</Paragraph>
    {admin&&<Card size="small" title="智能问答" style={{marginBottom:16}} extra={<Text type="secondary">用自然语言问系统，如「还有哪门必修课没排」</Text>}>
      <Space.Compact style={{width:'100%'}}>
        <Input aria-label="智能问答输入" placeholder="例如：这学期哪个教研室负荷最重？" value={qaQ} onChange={e=>setQaQ(e.target.value)} onPressEnter={()=>void askQa()}/>
        <Button type="primary" loading={qaBusy} onClick={()=>void askQa()}>提问</Button>
      </Space.Compact>
      {qaA&&<Alert style={{marginTop:8}} type="info" showIcon title={qaA}/>}
    </Card>}
    <Space wrap style={{marginBottom:20}}><Select aria-label="排课周期" style={{minWidth:260}} placeholder="选择排课周期" value={id} onChange={v=>{setState(undefined);setId(v);}} options={plans.map(p=>({value:p.id,label:`${p.name} · ${stateNames[p.state]}`}))}/>
      <Button onClick={()=>void load()}>刷新</Button>{section==='plan'&&admin&&<Button type="primary" onClick={()=>openModal('plan')}>新建排课周期</Button>}
    {section==='plan'&&admin&&state?.state==='draft'&&<><Text type="secondary">新增任务请从导入课程库拖入班级课表</Text><Button loading={busy} disabled={!tasks.length} onClick={()=>void action(()=>api.open(id!))}>开放教师填报</Button></>}
      {section==='review'&&can(user,'publish')&&state?.state==='matched'&&<Button loading={busy} onClick={()=>void action(()=>api.publish(id!))}>完整校验并发布</Button>}
      <ProfessionalExport/>
      {state?.state==='published'&&<Button onClick={async()=>{try{const blob=await api.export(id!);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`专业课表_周期${id}.xlsx`;a.click();URL.revokeObjectURL(url);}catch(e){message.error(e instanceof Error?e.message:'导出失败');}}}>导出已发布课表</Button>}
    </Space>
    {error&&<Alert type="error" showIcon title={error} style={{marginBottom:16}}/>}
    {admin&&state?.state==='published'&&<Card size="small" title="教师调课申请">
      {changeRequests.length?<Table rowKey="id" size="small" dataSource={changeRequests} pagination={{pageSize:5}} columns={[
        {title:'教师',dataIndex:'teacher_id',render:(value:number)=>profiles.find(p=>p.id===value)?.name||`教师${value}`},
        {title:'课程',dataIndex:'task_id',render:(value:number)=>taskName(value)},
        {title:'原因',dataIndex:'reason'}, {title:'期望调整',dataIndex:'desired_change',render:(v:string)=>v||'未填写'},
        {title:'状态',dataIndex:'status',render:(v:string)=>v==='pending'?'待处理':v==='approved'?'已批准':'已拒绝'},
        {title:'处理',render:(_,request:any)=>request.status==='pending'?<Space>
          <Button size="small" type="primary" onClick={()=>Modal.confirm({title:'批准调课申请',content:'系统将创建一个修订周期，不修改原发布快照。',onOk:()=>action(async()=>{await api.decideChangeRequest(id!,request.id,{approve:true,reason:'已批准，创建修订周期'});setChangeRequests(await api.changeRequests(id!));})})}>批准并创建修订周期</Button>
          <Button size="small" danger onClick={()=>Modal.confirm({title:'拒绝调课申请',content:'确认拒绝此申请并通知教师？',onOk:()=>action(async()=>{await api.decideChangeRequest(id!,request.id,{approve:false,reason:'经审核暂不调整'});setChangeRequests(await api.changeRequests(id!));})})}>拒绝</Button>
        </Space>:request.revision_plan_id?`修订周期 ${request.revision_plan_id}`:'—'},
      ]}/>:<Empty description="暂无调课申请"/>}
    </Card>}
    {loading?<Spin/>:loadedState?<><div style={{marginBottom:planInfoOpen?16:4}}>
      <Tooltip title={planInfoOpen?'收起周期信息':'展开周期信息'}><Button type="text" size="small" aria-label={planInfoOpen?'收起周期信息':'展开周期信息'} aria-expanded={planInfoOpen} icon={<InfoCircleOutlined/>} onClick={()=>setPlanInfoOpen(open=>!open)}/></Tooltip>
      {planInfoOpen&&<Alert type="info" showIcon style={{marginTop:6}} title={`${state.name} · ${stateNames[state.state]} · 修订${state.revision}`} description={`${state.global_cycle?`全学院所有专业与年级 · 第${state.academic_term}学期`:`${state.major||'未注明专业'} · ${gradeLabel(state.cohort)||'未注明年级'} · 第${state.semester}学期`}。开学日期：${state.opening_date||'未登记'}；第1教学周周一：${state.start_date}。W1—W${state.weeks}，考试周按年级设置。填报截止：${dayjs(state.deadline).format('YYYY-MM-DD HH:mm')}。${state.rule_confirmed?'匹配试算规则已由管理员确认':'评分规则尚未确认，禁止运行正式匹配'}`}/>}
    </div><Tabs key={section} items={tabs.filter(t=>section==='plan'?t.key==='pool':t.key==='match'||t.key==='profiles')}/></>:<Empty description={admin?'请新建周期并配置课程任务':'暂无已开放的选课计划，请等待管理员发布'}/>}
    <Modal title={modal==='plan'?'新建周期':modal==='task'?'设置阶段课程任务':'维护教师专业画像'} open={!!modal} onCancel={()=>setModal(null)} onOk={()=>void saveModal()} confirmLoading={busy} width={760} destroyOnHidden>
      <Form form={form} layout="vertical">
        {modal==='plan'&&<>
          <Form.Item name="name" label="周期名称" rules={[{required:true}]}><Input autoComplete="off"/></Form.Item>
          <Form.Item name="opening_date" label="开学日期（年、月、日）" rules={[{required:true,message:'请选择学校实际开学日期'}]} getValueProps={value=>({value:value?dayjs(value):null})} getValueFromEvent={value=>value?.format('YYYY-MM-DD')}>
            <DatePicker format="YYYY-MM-DD" placeholder="选择实际开学日期" style={{width:'100%'}} onChange={value=>{
              form.setFieldValue('start_date',value?suggestedMonday(value.format('YYYY-MM-DD')):undefined);
            }}/>
          </Form.Item>
          <Form.Item name="start_date" label="第1教学周周一" extra="选择开学日期后建议使用所在周的周一；如学校教学周起点不同，可自行调整。课表及导出均以此日期计算，周期学期随日期自动判断。" rules={[{required:true,message:'请确认第1教学周周一'},{validator:(_,value)=>!value||suggestedMonday(value)===value?Promise.resolve():Promise.reject(new Error('第1教学周必须从周一开始'))}]} getValueProps={value=>({value:value?dayjs(value):null})} getValueFromEvent={value=>value?.format('YYYY-MM-DD')}>
            <DatePicker format="YYYY-MM-DD" placeholder="确认教学周起点" style={{width:'100%'}} disabledDate={value=>value.day()!==1}/>
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="weeks" label="学期周数"><InputNumber min={18} max={20} style={{width:'100%'}}/></Form.Item></Col>
            <Col span={12}><Form.Item name="term" label="周期所属学期"><Select options={[{value:1,label:'上学期（第一学期）'},{value:2,label:'下学期（第二学期）'}]}/></Form.Item></Col>
          </Row>
          <Alert type="info" showIcon title="全学院全局周期" description="周期学期根据第1教学周日期自动建议，可手动调整为上学期或下学期。提交后按八学期学制筛出当前有效班级建立空白课表，并从课程管理匹配适用年级、专业和上课学期的活动课程。" style={{marginBottom:16}}/>
          {calendarRows.length>0&&<><Alert showIcon type="info" title="校历预览（公历，周一至周日）" description="自动处理跨月、跨年及闰年；节假日调课需另行安排。修改开学日期会重新建议教学周起点，请核对后保存。"/><Table aria-label="新周期校历预览" size="small" rowKey="week" dataSource={calendarRows} pagination={false} scroll={{y:240}} columns={[{title:'教学周',render:(_,r)=>`第${r.week}周`},{title:'周一',dataIndex:'start'},{title:'周日',dataIndex:'end'},{title:'安排',render:(_,r)=>r.exam?'考试周':'教学周'}]} style={{margin:'12px 0'}}/></>}
          <Form.Item name="deadline" label="意愿提交截止" rules={[{required:true}]}><Input type="datetime-local"/></Form.Item>
          <Alert type="info" title="默认匹配权重：团队40 / 方向20 / 领域15 / 曾授15 / 容量5（合计95）。管理员可在“匹配与审核”中调整权重；专业适配度独立计算。学期上限按不同课程代码计数。"/>
          <Form.Item name="rule_confirmed" valuePropName="checked"><Checkbox>已核对以上匹配规则，允许本周期运行匹配</Checkbox></Form.Item>
        </>}
        {modal==='task'&&editingTask&&<>
          <Alert type="info" showIcon title="课程基础信息按课程库只读展示" description="课程名称、编码、学分和学时请在课程管理中维护；周段由课表编排确定。地点和周内节次可留空，并可在正式公布前随时调整。" style={{marginBottom:16}}/>
          <Descriptions bordered size="small" column={2} items={[
            ...([['name','课程名称'],['code','课程编码'],['credits','学分'],['required_hours','计划学时'],['category','课程性质'],['department','所属专业'],['group','教学组']] as const).map(([key,label])=>({key,label,children:taskCourseInfo(editingTask)[key]??'未注明'})),
            {key:'actual_students',label:'实际选课人数',children:Number(editingTask.actual_student_count)>0?`${editingTask.actual_student_count}人`:'待学生选课结束后统计'},
          ]} style={{marginBottom:16}}/>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="teacher_count" label="教师人数" rules={[{required:true}]}><InputNumber min={1} max={5} style={{width:'100%'}}/></Form.Item></Col>
            <Col span={12}><Form.Item name="max_students" label="学生上限" rules={[{required:true}]} extra="仅设置课程人数上限；实际学生数待排课完成、学生选课结束后统计。"><InputNumber min={1} max={10000} style={{width:'100%'}}/></Form.Item></Col>
          </Row>
          <Form.Item name="room_id" label="上课地点" extra="从教室管理选择，可暂不分配。">
            <Select allowClear showSearch optionFilterProp="label" loading={roomsLoading} placeholder="选择教室" options={rooms.map(room=>({value:room.id,disabled:!room.is_available,label:`${[room.building,room.floor!=null?`${room.floor}层`:null,room.name].filter(Boolean).join(' · ')}（${room.capacity}人）${room.is_available?'':' · 已停用'}`}))}/>
          </Form.Item>
          <Form.List name="slots">
            {(fields,{add,remove})=><Space direction="vertical" style={{width:'100%'}}>
              <Text strong>周内授课时间</Text>
              <Text type="secondary">系统按课程节次和班级占用自动初排；可留空，或在正式公布前调整。</Text>
              {fields.map(({key,name,...rest})=><Space key={key} align="baseline" wrap>
                <Form.Item {...rest} name={[name,'day']} rules={[{required:true,message:'请选择星期'}]}><Select aria-label={`第${name+1}个时段星期`} style={{width:110}} options={Array.from({length:7},(_,index)=>({value:index+1,label:`周${'一二三四五六日'[index]}`}))}/></Form.Item>
                <Form.Item {...rest} name={[name,'start']} rules={[{required:true,message:'请选择起始节次'}]}><Select aria-label={`第${name+1}个时段起始节次`} style={{width:120}} options={Array.from({length:8},(_,index)=>({value:index+1,label:`第${index+1}节起`}))}/></Form.Item>
                <Form.Item {...rest} name={[name,'count']} rules={[{required:true,message:'请选择每周节数'}]}><Select aria-label={`第${name+1}个时段连续节数`} style={{width:120}} options={Array.from({length:8},(_,index)=>({value:index+1,label:`连续${index+1}节`}))}/></Form.Item>
                <Form.Item {...rest} name={[name,'phase']} rules={[{required:true,message:'请选择周段'}]}><Select aria-label={`第${name+1}个时段周段`} style={{width:130}} options={[{value:'normal',label:'常规周'},{value:'tail',label:'尾段周'}]}/></Form.Item>
                <Button aria-label={`删除第${name+1}个授课时段`} type="text" danger icon={<DeleteOutlined/>} onClick={()=>remove(name)}/>
              </Space>)}
              <Button type="dashed" icon={<PlusOutlined/>} onClick={()=>add({day:1,start:1,count:1,phase:'normal'})}>添加授课时段</Button>
            </Space>}
          </Form.List>
        </>}
        {modal==='profile'&&<>
          <Alert type="info" title="教师自填专业资料优先用于匹配；此处维护团队、曾授和负荷记录，不能覆盖教师个人资料。"/><Form.Item name="direction" label="管理登记方向（未自填时使用）"><Input/></Form.Item><Form.Item name="tags" label="管理登记领域（未自填时使用）"><Input/></Form.Item>
          <Form.Item name="team_codes" label="已核实团队课程编码"><Input/></Form.Item><Form.Item name="taught_codes" label="已核实曾授课程编码"><Input/></Form.Item>
          <Form.Item name="weekly_limit" label="每周上限（节）"><InputNumber min={0} max={40}/></Form.Item><Form.Item name="course_limit" label="学期不同课程数上限"><InputNumber min={1} max={30}/></Form.Item>
          <Form.Item name="external_hours" label={'逐周外部课时，例如 {"1":8,"2":8}'}><Input.TextArea rows={3}/></Form.Item>
          <Form.Item name="verified" valuePropName="checked"><Checkbox>团队、曾授记录及课时容量已核实</Checkbox></Form.Item>
        </>}
      </Form>
    </Modal>
    <Modal title={`自动构建画像 · ${autoBuild?.teacher?.name||''}`} open={!!autoBuild} onCancel={()=>setAutoBuild(undefined)} onOk={()=>void confirmAutoBuild()} confirmLoading={busy} okText="确认写入画像" width={640} destroyOnHidden>
      {autoBuild&&<Space direction="vertical" size="middle" style={{width:'100%'}}>
        <Alert type={autoBuild.result?.source==='llm'?'success':'info'} showIcon
          title={autoBuild.result?.source==='llm'?'已由 AI 结合历史授课记录生成':'未配置 AI，按历史授课记录汇总'}
          description={autoBuild.result?.reason}/>
        <Descriptions bordered size="small" column={1} items={[
          {key:'direction',label:'专业方向',children:autoBuild.result?.proposal?.direction||'—'},
          {key:'tags',label:'领域标签',children:(autoBuild.result?.proposal?.tags||[]).join('、')||'—'},
          {key:'skilled',label:'擅长课程',children:(autoBuild.result?.proposal?.skilled_courses||[]).join('、')||'—'},
          {key:'taught',label:'曾授课程编码',children:(autoBuild.result?.proposal?.taught_codes||[]).join('、')||'—'},
          {key:'rationale',label:'依据',children:autoBuild.result?.proposal?.rationale||'—'},
        ]}/>
      </Space>}
    </Modal>
    <Modal title="AI 匹配理由" open={!!matchExplain} onCancel={()=>setMatchExplain(undefined)} footer={<Button onClick={()=>setMatchExplain(undefined)}>关闭</Button>} width={680} destroyOnHidden>
      {matchExplain&&<Space direction="vertical" size="middle" style={{width:'100%'}}>
        <Alert type={matchExplain.source==='llm'?'success':'info'} showIcon
          title={matchExplain.source==='llm'?'已由 AI 生成推荐理由':'未配置 AI，展示规则理由'}
          description={matchExplain.reason}/>
        <Table rowKey={(r:any)=>`${r.task_id}-${r.teacher_id}`} size="small" dataSource={matchExplain.items||[]} pagination={false}
          columns={[
            {title:'课程',render:(_,r:any)=>taskName(r.task_id)},
            {title:'教师',dataIndex:'teacher_name'},
            {title:'推荐理由',dataIndex:'reason'},
          ]}/>
      </Space>}
    </Modal>
  </div>;
}

export default function PlanningWorkspace(){
  const {user}=useAuth();
  return can(user,'admin')?<ManagementPlanningWorkspace/>:can(user,'teaching')?<TeacherSelectionPage/>:<ManagementPlanningWorkspace section="review"/>;
}
