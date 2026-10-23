import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Col, DatePicker, Descriptions, Empty, Form, Input, InputNumber, message,
  Modal, Row, Select, Space, Spin, Table, Tabs, Tag, Tooltip, Typography } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi as api } from '../api/planning';
import { classApi } from '../api/client';
import ProfessionalExport from '../components/ProfessionalExport';
import TeacherSelectionPage from './TeacherSelectionPage';
import { taskLimitsPayload, taskCourseInfo } from '../lib/taskForm';
import { gradeLabel } from '../lib/adminStageGrid';
import { academicCalendar, suggestedMonday } from '../lib/academicCalendar';
import AdminStagePlanner from '../components/AdminStagePlanner';
import ReviewTimetable from '../components/ReviewTimetable';
import MatchWeightsPanel from '../components/MatchWeightsPanel';

const { Title, Text, Paragraph } = Typography;
const stateNames: Record<string,string> = { draft:'计划草稿', open:'开放填报', matched:'匹配待审核', published:'已发布' };
const textList = (s: string | string[]) => Array.isArray(s) ? s : (s || '').split(/[,，\n]/).map(x => x.trim()).filter(Boolean);

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
  const [form]=Form.useForm();
  const calendarStart=Form.useWatch('start_date',form);
  const calendarWeeks=Form.useWatch('weeks',form);
  const calendarRows=academicCalendar(calendarStart||'',calendarWeeks||20);
  useEffect(()=>{
    if(calendarStart)form.setFieldValue('term',dayjs(calendarStart).month()>=7||dayjs(calendarStart).month()===0?1:2);
  },[calendarStart,form]);
  const [reviewReason,setReviewReason]=useState('已核对专业领域和实际负荷');
  const [changeRequests,setChangeRequests]=useState<any[]>([]);

  const load = useCallback(async () => {
    setError('');
    try {
      const list=await api.plans();setPlans(list);
      const target=id ?? list[0]?.id;
      if(target) { if(!id)setId(target); setState(await api.state(target,section==='review'&&!admin)); } else setState(undefined);
      if(admin){ const [p,c]=await Promise.all([api.profiles(),classApi.list({limit:500})]);setProfiles(p);setClasses(c); }
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
  const openModal=(type:'plan'|'task'|'profile',p?:any)=>{
    form.resetFields();setModal(type);setProfileId(p?.id);
    setEditingTask(type==='task'?p:undefined);
    if(type==='plan')form.setFieldsValue({weeks:20,term:(dayjs().month()>=7||dayjs().month()===0)?1:2,rule_confirmed:false,groups:[]});
    if(type==='task'&&p)form.setFieldsValue({
      teacher_count:p.teacher_count??1,
      max_students:p.max_students??30,
    });
    if(type==='profile')form.setFieldsValue({...p,tags:(p.tags||[]).join('，'),team_codes:(p.team_codes||[]).join('，'),taught_codes:(p.taught_codes||[]).join('，'),external_hours:JSON.stringify(p.external_hours||{})});
  };
  const saveModal=async()=>{
    const v=await form.validateFields();
    setBusy(true);
    try{
      if(modal==='plan'){const p=await api.createPlan({...v,global_cycle:true,deadline:new Date(v.deadline).toISOString()});setId(p.id);}
      if(modal==='task'){
        if(!editingTask)throw new Error('请先从导入课程库拖入任务');
        await api.setTaskLimits(id!,editingTask.id,taskLimitsPayload(v,state.revision));
      }
      if(modal==='profile')await api.saveProfile(profileId!,{...v,tags:textList(v.tags),team_codes:textList(v.team_codes),taught_codes:textList(v.taught_codes),external_hours:JSON.parse(v.external_hours||'{}')});
      setModal(null);await load();message.success('已保存');
    }catch(e){message.error(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
  };
  const tasks:any[]=state?.tasks||[];
  const taskName=(taskId:number)=>tasks.find(t=>t.id===taskId)?.name||String(taskId);

  const matchView=<Space orientation="vertical" size="large" style={{width:'100%'}}>
    <Alert showIcon type="info" title={admin?'系统自动匹配 + 人工审核调剂':'教研室主任审核'} description={admin?`综合推荐按当前权重合计 ${state.match_weight_total??95} 分计算；专业适配度只使用方向和领域。系统按规则自动匹配并落位，管理员可在下方实时全学院课表中核对申报教师并人工调剂。`:'可查看并审核授权专业方向的课程任务；匹配由学院管理员统一运行。'}/>
    {admin&&<Card size="small" title="匹配权重设置" style={{marginBottom:16}}>
      <MatchWeightsPanel plan={state} disabled={busy} onSaved={load}/>
    </Card>}
    {admin&&<Space wrap><Button type="primary" loading={busy} disabled={!state.rule_confirmed||!['open','matched'].includes(state.state)} onClick={()=>void action(()=>api.match(id!))}>运行系统匹配（自动落位） / 保留锁定重跑</Button><Text>已提交教师：{state.submission_count??'—'}</Text></Space>}
    {state.match?<Table rowKey={r=>`${r.task_id}-${r.teacher_id}`} dataSource={state.match.candidates} pagination={false} scroll={{x:760}}
      columns={[
        {title:'课程任务',render:(_,r:any)=>`${taskName(r.task_id)} · ${tasks.find(t=>t.id===r.task_id)?.group}`},
        {title:'教师',render:(_,r:any)=>r.teacher_name},
        {title:'专业适配度',render:(_,r:any)=>r.professional_fit==null?<Tag color="orange">资料待核实</Tag>:`${r.professional_fit}%`},
        {title:'综合推荐',render:(_,r:any)=>r.raw_total==null?'待核实':`${r.raw_total}/${r.maximum??state.match?.maximum??state.match_weight_total??95} (${r.normalized_total}%)`},
        {title:'硬约束',render:(_,r:any)=>r.eligible?<Tag color="green">可审核</Tag>:<Text type="danger">{r.reasons.join('；')}</Text>},
      ]} expandable={{expandedRowRender:(r:any)=><Space wrap>{r.components.map((c:any)=><Tag key={c.name}>{c.name}：{c.score??'未知'}/{c.maximum}{c.hits?.length?` · 命中${c.hits.join('、')}`:''}</Tag>)}</Space>}}/>:<Empty description="尚未运行匹配"/>}
    {review&&<Card title={admin?'全学院实时课表与人工调剂':'本教研室课程审核'} extra={<Text type="secondary">教研室主任仅查看并审核授权专业方向的课程任务</Text>}>
      <Space wrap style={{marginBottom:12,width:'100%'}}>
        <Text strong>调剂说明</Text>
        <Input aria-label="调剂说明" value={reviewReason} onChange={e=>setReviewReason(e.target.value)} placeholder="审核依据与改选原因" style={{minWidth:320,flex:1}}/>
      </Space>
      <ReviewTimetable plan={state} tasks={tasks} match={state.match} busy={busy}
        canAssign={state.state==='matched'&&Boolean(state.match)} reason={reviewReason}
        onAssign={(task,teacher_ids)=>void action(()=>api.reassign(id!,task.id,{teacher_ids,match_id:state.match.id,reason:reviewReason}))}/>
    </Card>}
  </Space>;

  const tabs:any[]=[];
  if(admin)tabs.push({key:'pool',label:'课程表编排',children:<AdminStagePlanner key={state.id} plan={state} classes={classes} onChange={load} onEdit={task=>openModal('task',task)}/>});
  tabs.push({key:'match',label:review?'匹配与审核':'我的匹配结果',children:matchView});
  if(admin)tabs.push({key:'profiles',label:'教师专业画像',children:<Table rowKey="id" dataSource={profiles} pagination={false} columns={[{title:'教师',dataIndex:'name'},{title:'方向',dataIndex:'direction'},{title:'领域',render:(_,p:any)=>p.tags.join('、')},{title:'资料来源',render:(_,p:any)=>p.professional_profile_source==='self_declared'?'教师自填':'管理员登记'},{title:'管理记录核实',render:(_,p:any)=>p.verified?'已核对':'待核对'},{title:'操作',render:(_,p:any)=><Button onClick={()=>openModal('profile',p)}>维护画像 / 外部课时</Button>}]}/>});

  return <div>
    <Title level={3}>{section==='plan'?'排课周期计划':!admin&&user?.grants?.some(g=>g.capability==='lead')?'教研室主任审核':'匹配与审核'}</Title>
    <Paragraph>教师先选课并提交意愿，系统提供专业匹配依据，审核确认后分配。每教学组同周最多2门、同日1门。</Paragraph>
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
          <Alert type="info" showIcon title="课程基础信息按课程库只读展示" description="课程名称、编码、学分和学时请在课程管理中维护；周段由课表编排确定，此处设置教师人数与学生上限。" style={{marginBottom:16}}/>
          <Descriptions bordered size="small" column={2} items={[
            ...([['name','课程名称'],['code','课程编码'],['credits','学分'],['required_hours','计划学时'],['category','课程性质'],['department','所属专业'],['group','教学组']] as const).map(([key,label])=>({key,label,children:taskCourseInfo(editingTask)[key]??'未注明'})),
            {key:'actual_students',label:'实际选课人数',children:Number(editingTask.actual_student_count)>0?`${editingTask.actual_student_count}人`:'待学生选课结束后统计'},
          ]} style={{marginBottom:16}}/>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="teacher_count" label="教师人数" rules={[{required:true}]}><InputNumber min={1} max={5} style={{width:'100%'}}/></Form.Item></Col>
            <Col span={12}><Form.Item name="max_students" label="学生上限" rules={[{required:true}]} extra="仅设置课程人数上限；实际学生数待排课完成、学生选课结束后统计。"><InputNumber min={1} max={10000} style={{width:'100%'}}/></Form.Item></Col>
          </Row>
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
  </div>;
}

export default function PlanningWorkspace(){
  const {user}=useAuth();
  return can(user,'admin')?<ManagementPlanningWorkspace/>:can(user,'teaching')?<TeacherSelectionPage/>:<ManagementPlanningWorkspace section="review"/>;
}
