import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Col, Empty, Form, Input, InputNumber, message,
  Modal, Row, Select, Space, Spin, Table, Tabs, Tag, Typography } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi as api } from '../api/planning';
import { classroomApi } from '../api/client';
import StageTimetable from '../components/StageTimetable';
import ProfessionalExport from '../components/ProfessionalExport';
import TeacherSelectionPage from './TeacherSelectionPage';
import AdminStagePlanner from '../components/AdminStagePlanner';

const { Title, Text, Paragraph } = Typography;
const stateNames: Record<string,string> = { draft:'计划草稿', open:'开放填报', matched:'匹配待审核', published:'已发布' };
const days=['周一','周二','周三','周四','周五','周六','周日'];
const textList = (s: string | string[]) => Array.isArray(s) ? s : (s || '').split(/[,，\n]/).map(x => x.trim()).filter(Boolean);

export function ManagementPlanningWorkspace() {
  const { user }=useAuth();
  const admin=can(user,'admin'), review=can(user,'review'), teaching=can(user,'teaching');
  const [plans,setPlans]=useState<any[]>([]), [id,setId]=useState<number>(), [loadedState,setState]=useState<any>();
  const state=loadedState||{state:'',draft:{revision:0,task_ids:[]},match:null,rule_confirmed:false};
  const [profiles,setProfiles]=useState<any[]>([]), [rooms,setRooms]=useState<any[]>([]);
  const [busy,setBusy]=useState(false), [loading,setLoading]=useState(true), [error,setError]=useState('');
  const [modal,setModal]=useState<'plan'|'task'|'profile'|null>(null), [profileId,setProfileId]=useState<number>();
  const [editingTask,setEditingTask]=useState<any>();
  const [form]=Form.useForm(), [selectedTeachers,setSelectedTeachers]=useState<Record<number,number[]>>({});
  const [reviewReason,setReviewReason]=useState('已核对专业领域、志愿和实际负荷');

  const load = useCallback(async () => {
    setError('');
    try {
      const list=await api.plans();setPlans(list);
      const target=id ?? list[0]?.id;
      if(target) { if(!id)setId(target); setState(await api.state(target)); } else setState(undefined);
      if(admin){ const [p,r]=await Promise.all([api.profiles(),classroomApi.list({limit:500})]);setProfiles(p);setRooms(r); }
    }catch(e){setError(e instanceof Error?e.message:'加载失败');}finally{setLoading(false);}
  },[id,admin]);
  useEffect(()=>{void load();},[load]);

  const action=async(fn:()=>Promise<unknown>)=>{
    setBusy(true);try{await fn();await load();message.success('已保存');}catch(e){message.error(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}
  };
  const openModal=(type:'plan'|'task'|'profile',p?:any)=>{
    form.resetFields();setModal(type);setProfileId(p?.id);
    setEditingTask(type==='task'?p:undefined);
    if(type==='plan')form.setFieldsValue({name:'2026级视觉传达 · 第2学期',start_date:'2027-02-01',weeks:20,deadline:'2027-01-31T23:59',rule_confirmed:false,major:'视觉传达设计',cohort:'2026',semester:2,groups:'视传2601，视传2602，视传2603，视传2604'});
    if(type==='task')form.setFieldsValue({credits:2,required_hours:32,group:'视传2601',department:'视觉传达设计',teacher_count:1,student_count:30,mode:'single',profile_verified:false,...p,start_week:p?.start_week||1,end_week:p?.end_week||4,slots:p?.slots?.length?p.slots:[{day:1,start:1,count:8}],tags:(p?.tags||[]).join('，')});
    if(type==='profile')form.setFieldsValue({...p,tags:(p.tags||[]).join('，'),team_codes:(p.team_codes||[]).join('，'),taught_codes:(p.taught_codes||[]).join('，'),external_hours:JSON.stringify(p.external_hours||{})});
  };
  const saveModal=async()=>{
    const v=await form.validateFields();
    setBusy(true);
    try{
      if(modal==='plan'){const p=await api.createPlan({...v,groups:textList(v.groups),deadline:new Date(v.deadline).toISOString()});setId(p.id);}
      if(modal==='task'){
        const payload={...v,tags:textList(v.tags||''),room_id:v.room_id||null,source:editingTask?.source||{}};
        if(editingTask)await api.editTask(id!,editingTask.id,payload);else await api.addTask(id!,payload);
      }
      if(modal==='profile')await api.saveProfile(profileId!,{...v,tags:textList(v.tags),team_codes:textList(v.team_codes),taught_codes:textList(v.taught_codes),external_hours:JSON.parse(v.external_hours||'{}')});
      setModal(null);await load();message.success('已保存');
    }catch(e){message.error(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}
  };
  const saveChoices=(ids:number[])=>action(()=>api.saveDraft(id!,{revision:state.draft.revision,plan_revision:state.revision,task_ids:ids}));
  const choices:number[]=state?.draft?.task_ids||[];
  const toggle=(taskId:number)=>saveChoices(choices.includes(taskId)?choices.filter(x=>x!==taskId):[...choices,taskId]);
  const reorder=(index:number,delta:number)=>{const next=[...choices];[next[index],next[index+delta]]=[next[index+delta],next[index]];void saveChoices(next);};
  const tasks:any[]=state?.tasks||[];
  const taskName=(taskId:number)=>tasks.find(t=>t.id===taskId)?.name||String(taskId);
  const mine=tasks.filter(t=>t.teacher_ids.includes(user?.teacher_id));
  const slotText=(t:any)=>t.slots.map((s:any)=>`${s.phase==='tail'?'尾段 ':''}${days[s.day-1]} 第${s.start}—${s.start+s.count-1}节`).join(' · ');
  const cards=<Row gutter={[16,16]}>{tasks.map(t=><Col xs={24} lg={12} key={t.id}>
    <Card title={<Space wrap>{t.name}<Tag>{t.group}</Tag><Tag>{t.mode==='collaborative'?'同堂协作':t.mode==='group'?'分组':t.mode==='segment'?'分段':'独立任务'}</Tag></Space>}
      extra={teaching&&state.state==='open'?<Checkbox aria-label={`预选 ${t.code} ${t.group}`} checked={choices.includes(t.id)} disabled={busy||(!choices.includes(t.id)&&choices.length>=5)} onChange={()=>void toggle(t.id)}>预选</Checkbox>:null}>
      <Paragraph>{t.code} · {t.credits}学分 · {t.required_hours}学时 · {t.start_week?`W${t.start_week}—W${t.end_week}`:'周段待配置'}</Paragraph>
      <Paragraph>{slotText(t)}</Paragraph>
      <Paragraph>专业领域：{t.direction||'待完善'} / {(t.tags||[]).join('、')||'待完善'}</Paragraph>
      <Space wrap><Tag color={t.room_id?'blue':'default'}>地点：{t.room_name||rooms.find(r=>r.id===t.room_id)?.name||(t.room_id?`地点${t.room_id}`:'待指定')}</Tag><Tag>教师名额 {t.teacher_count}</Tag></Space>
      <Paragraph style={{marginTop:10,marginBottom:0}}>任课教师：{t.teacher_names?.length?t.teacher_names.join('、'):'待分配（预选不占名额）'}</Paragraph>
      {admin&&state.state==='draft'&&<Button style={{marginTop:12}} onClick={()=>openModal('task',t)}>编辑周段、节次与地点</Button>}
    </Card>
  </Col>)}</Row>;

  const basket=<Card title={`我的预选草稿 · ${choices.length}/5项`}>
    <Alert showIcon type="info" title="仅本人可见，保存草稿后仍需提交" description="可跨专业、教研室选择。预选意愿不是任课资格；匹配后需有权人员审核。" style={{marginBottom:16}} />
    {choices.length?choices.map((taskId,index)=><div key={taskId} style={{padding:'12px 0',borderBottom:'1px solid #eee'}}>
      <Space wrap><Tag>志愿{index+1}</Tag><Text>{taskName(taskId)}</Text>
        <Button size="small" aria-label={`上移志愿${index+1}`} icon={<ArrowUpOutlined/>} disabled={busy||index===0||state.state!=='open'} onClick={()=>reorder(index,-1)}/>
        <Button size="small" aria-label={`下移志愿${index+1}`} icon={<ArrowDownOutlined/>} disabled={busy||index===choices.length-1||state.state!=='open'} onClick={()=>reorder(index,1)}/>
        <Button size="small" disabled={busy||state.state!=='open'} onClick={()=>void toggle(taskId)}>移除</Button>
      </Space>
    </div>):<Empty description="在课程卡片上点选预选"/>}
    <Space wrap style={{marginTop:20}}><Tag color={busy?'orange':'green'}>{busy?'保存中':'服务端草稿版本 '+state.draft.revision}</Tag>
      <Button type="primary" loading={busy} disabled={!choices.length||state.state!=='open'} onClick={()=>Modal.confirm({title:'提交当前志愿？',content:'提交后管理员可查看；匹配前在截止时间内可修改并再次提交。',onOk:()=>action(()=>api.submit(id!,state.draft.revision))})}>提交志愿</Button>
    </Space>
    <Paragraph style={{marginTop:16}}>最近提交：{state.submission?`批次${state.submission.id}，${state.submission.task_ids.map(taskName).join('、')}`:'尚未提交'}</Paragraph>
  </Card>;

  const matchView=<Space orientation="vertical" size="large" style={{width:'100%'}}>
    <Alert showIcon type="info" title="专业适配度与综合推荐分分开展示" description="六项原始满分105，专业适配只使用方向和领域。资料不足显示待核实；匹配建议不等于任课分配。"/>
    {review&&<Space wrap><Button type="primary" loading={busy} disabled={!state.rule_confirmed||!['open','matched'].includes(state.state)} onClick={()=>void action(()=>api.match(id!))}>运行匹配 / 保留锁定重跑</Button><Text>已提交教师：{state.submission_count??'—'}</Text></Space>}
    {state.match?<Table rowKey={r=>`${r.task_id}-${r.teacher_id}`} dataSource={state.match.candidates} pagination={false} scroll={{x:760}}
      columns={[
        {title:'课程任务',render:(_,r:any)=>`${taskName(r.task_id)} · ${tasks.find(t=>t.id===r.task_id)?.group}`},
        {title:'教师 / 志愿',render:(_,r:any)=>`${r.teacher_name} / 第${r.rank}志愿`},
        {title:'专业适配度',render:(_,r:any)=>r.professional_fit==null?<Tag color="orange">资料待核实</Tag>:`${r.professional_fit}%`},
        {title:'综合推荐',render:(_,r:any)=>r.raw_total==null?'待核实':`${r.raw_total}/105 (${r.normalized_total}%)`},
        {title:'硬约束',render:(_,r:any)=>r.eligible?<Tag color="green">可审核</Tag>:<Text type="danger">{r.reasons.join('；')}</Text>},
      ]} expandable={{expandedRowRender:(r:any)=><Space wrap>{r.components.map((c:any)=><Tag key={c.name}>{c.name}：{c.score??'未知'}/{c.maximum}{c.hits?.length?` · 命中${c.hits.join('、')}`:''}</Tag>)}</Space>}}/>:<Empty description="尚未运行匹配"/>}
    {review&&state.match&&<Card title="审核分配（确认后锁定，重跑不会覆盖）">
      <Input aria-label="审核说明" value={reviewReason} onChange={e=>setReviewReason(e.target.value)} placeholder="审核依据与改选原因" style={{marginBottom:16}}/>
      {tasks.map(t=>{
        const candidates=state.match.candidates.filter((c:any)=>c.task_id===t.id&&c.eligible);
        const suggested=state.match.suggestions.find((s:any)=>s.task_id===t.id)?.teacher_ids||[];
        return <div key={t.id} style={{marginBottom:18}}><Space wrap><Text strong>{t.name} / {t.group}</Text><Tag>需要{t.teacher_count}人</Tag>
          {t.locked?<Tag color="green">已锁定：{t.teacher_names.join('、')}</Tag>:<>
            <Select mode="multiple" aria-label={`审核教师 ${t.code}`} style={{minWidth:250}} placeholder={suggested.length?`系统建议：${suggested.map((x:number)=>candidates.find((c:any)=>c.teacher_id===x)?.teacher_name).join('、')}`:'待人工选择'}
              value={selectedTeachers[t.id]||[]} onChange={v=>setSelectedTeachers({...selectedTeachers,[t.id]:v})}
              options={candidates.map((c:any)=>({value:c.teacher_id,label:`${c.teacher_name} · ${c.professional_fit??'待核实'}`}))}/>
            <Button loading={busy} disabled={(selectedTeachers[t.id]||[]).length!==t.teacher_count||!reviewReason.trim()} onClick={()=>void action(()=>api.assign(id!,{task_id:t.id,teacher_ids:selectedTeachers[t.id],match_id:state.match.id,reason:reviewReason}))}>审核通过并锁定</Button>
          </>}
        </Space></div>;
      })}
    </Card>}
  </Space>;

  const tabs:any[]=[];
  tabs.push({key:'pool',label:admin?'课程表编排':'待选课程库',children:admin?<AdminStagePlanner key={state.id} plan={state} rooms={rooms} onChange={load} onEdit={t=>openModal('task',t)}/>:tasks.length?<><StageTimetable tasks={tasks} weeks={state.weeks||20} selected={choices} disabled={busy||!(teaching&&state.state==='open'||admin&&state.state==='draft')} onTask={t=>{if(admin&&state.state==='draft')openModal('task',t);else if(choices.length<5||choices.includes(t.id))void toggle(t.id);else message.warning('最多5项意愿');}}/>{cards}</>:<Empty description="管理员尚未生成完整课程任务"/>});
  if(teaching)tabs.push({key:'draft',label:'我的草稿与提交',children:basket});
  tabs.push({key:'match',label:review?'匹配与审核':'我的匹配结果',children:matchView});
  if(teaching)tabs.push({key:'mine',label:'我的授课任务',children:mine.length?<Table rowKey="id" dataSource={mine} pagination={false} columns={[{title:'课程',dataIndex:'name'},{title:'班级/组',dataIndex:'group'},{title:'周段',render:(_,t:any)=>`W${t.start_week}—${t.end_week}`},{title:'时段',render:(_,t:any)=>slotText(t)},{title:'状态',render:()=>stateNames[state.state]}]}/>:<Empty description="暂无审核确认的本人任务"/>});
  if(admin)tabs.push({key:'profiles',label:'教师专业画像',children:<Table rowKey="id" dataSource={profiles} pagination={false} columns={[{title:'教师',dataIndex:'name'},{title:'方向',dataIndex:'direction'},{title:'领域',render:(_,p:any)=>p.tags.join('、')},{title:'资料来源',render:(_,p:any)=>p.professional_profile_source==='self_declared'?'教师自填':'管理员登记'},{title:'管理记录核实',render:(_,p:any)=>p.verified?'已核对':'待核对'},{title:'操作',render:(_,p:any)=><Button onClick={()=>openModal('profile',p)}>维护画像 / 外部课时</Button>}]}/>});

  return <div>
    <Title level={3}>{teaching?'我的教学任务':'专业课计划与教师意愿审核'}</Title>
    <Paragraph>教师先选课并提交意愿，系统提供专业匹配依据，审核确认后分配。每教学组同周最多2门、同日1门。</Paragraph>
    <Space wrap style={{marginBottom:20}}><Select aria-label="排课周期" style={{minWidth:260}} placeholder="选择排课周期" value={id} onChange={v=>{setState(undefined);setId(v);setSelectedTeachers({});}} options={plans.map(p=>({value:p.id,label:`${p.name} · ${stateNames[p.state]}`}))}/>
      <Button onClick={()=>void load()}>刷新</Button>{admin&&<Button type="primary" onClick={()=>openModal('plan')}>新建排课周期</Button>}
      {admin&&state?.state==='draft'&&<><Button onClick={()=>openModal('task')}>新增课程任务</Button><Button loading={busy} disabled={!tasks.length} onClick={()=>void action(()=>api.open(id!))}>开放教师填报</Button></>}
      {can(user,'publish')&&state?.state==='matched'&&<Button loading={busy} onClick={()=>void action(()=>api.publish(id!))}>完整校验并发布</Button>}
      <ProfessionalExport/>
      {state?.state==='published'&&<Button onClick={async()=>{try{const blob=await api.export(id!);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`专业课表_周期${id}.xlsx`;a.click();URL.revokeObjectURL(url);}catch(e){message.error(e instanceof Error?e.message:'导出失败');}}}>导出已发布课表</Button>}
    </Space>
    {error&&<Alert type="error" showIcon title={error} style={{marginBottom:16}}/>}
    {loading?<Spin/>:loadedState?<><Alert type="info" showIcon style={{marginBottom:16}} title={`${state.name} · ${stateNames[state.state]} · 修订${state.revision}`} description={`W1—W${state.weeks}，最后一周考试（20周周期为第20周）。填报截止：${dayjs(state.deadline).format('YYYY-MM-DD HH:mm')}。${state.rule_confirmed?'匹配试算规则已由管理员确认':'评分规则尚未确认，禁止运行正式匹配'}`}/><Tabs items={tabs}/></>:<Empty description={admin?'请新建周期并配置课程任务':'暂无已开放的选课计划，请等待管理员发布'}/>}
    <Modal title={modal==='plan'?'新建周期':modal==='task'?'设置阶段课程任务':'维护教师专业画像'} open={!!modal} onCancel={()=>setModal(null)} onOk={()=>void saveModal()} confirmLoading={busy} width={760} destroyOnHidden>
      <Form form={form} layout="vertical">
        {modal==='task'&&editingTask?.source?.course_metadata&&<Alert type="info" showIcon title="培养方案原始授课要求（请据此配置阶段和节次）" description={`周课时：${editingTask.source.course_metadata.weekly_hours??'未注明'}；上课周数：${editingTask.source.course_metadata.teaching_weeks??'未注明'}；备注：${editingTask.source.course_metadata.notes||'无'}。系统未自动猜定起始周。`} style={{marginBottom:16}}/>}
        {modal==='plan'&&<>
          <Form.Item name="name" label="周期名称" rules={[{required:true}]}><Input/></Form.Item>
          <Form.Item name="start_date" label="第1周周一日期" rules={[{required:true}]}><Input type="date"/></Form.Item>
          <Form.Item name="weeks" label="学期周数"><InputNumber min={18} max={20}/></Form.Item>
          <Form.Item name="deadline" label="意愿提交截止" rules={[{required:true}]}><Input type="datetime-local"/></Form.Item>
          <Row gutter={12}><Col span={8}><Form.Item name="major" label="适用专业"><Input/></Form.Item></Col><Col span={8}><Form.Item name="cohort" label="入学届次"><Input/></Form.Item></Col><Col span={8}><Form.Item name="semester" label="培养学期"><InputNumber min={1} max={12}/></Form.Item></Col></Row>
          <Form.Item name="groups" label="教学组/班级（逗号分隔）"><Input/></Form.Item>
          <Alert type="info" title="试算规则：团队40 / 方向20 / 领域15 / 曾授15 / 志愿10—1 / 容量5；原始满分105，专业分独立归一。学期上限按不同课程代码计数。"/>
          <Form.Item name="rule_confirmed" valuePropName="checked"><Checkbox>已核对以上匹配规则，允许本周期运行匹配</Checkbox></Form.Item>
        </>}
        {modal==='task'&&<>
          <Row gutter={16}>{[['name','课程名称'],['code','课程编码'],['group','教学组'],['department','课程归属教研室'],['direction','专业方向']].map(([name,label])=><Col span={12} key={name}><Form.Item name={name} label={label} rules={[{required:name!=='direction'}]}><Input/></Form.Item></Col>)}</Row>
          <Form.Item name="tags" label="课程领域标签（逗号分隔）"><Input/></Form.Item>
          <Row gutter={16}>{[['credits','学分',0,30],['required_hours','计划学时',1,400],['start_week','起始周',1,19],['end_week','结束周',1,19],['teacher_count','教师名额',1,5],['student_count','人数',1,200],['tail_weeks','尾段周数',0,18]].map(([name,label,min,max])=><Col span={8} key={name}><Form.Item name={String(name)} label={String(label)} rules={[{required:true}]}><InputNumber min={Number(min)} max={Number(max)}/></Form.Item></Col>)}</Row>
          <Form.Item name="mode" label="授课模式"><Select options={[{value:'single',label:'独立任务'},{value:'segment',label:'分段（分别建立各阶段任务）'},{value:'group',label:'分组（分别建立各学生组任务）'},{value:'collaborative',label:'同堂协作（多教师共同占用时段）'}]}/></Form.Item>
          <Form.List name="slots">{(fields,{add,remove})=><><Text strong>周内连续节次（自动核对总学时）</Text>{fields.map(f=><Space key={f.key} align="baseline"><Form.Item name={[f.name,'phase']} initialValue="normal"><Select style={{width:90}} options={[{value:'normal',label:'正常周'},{value:'tail',label:'尾段周'}]}/></Form.Item><Form.Item name={[f.name,'day']} rules={[{required:true}]}><Select style={{width:100}} options={days.map((d,i)=>({value:i+1,label:d}))}/></Form.Item><Form.Item name={[f.name,'start']} label="起始节"><InputNumber min={1} max={8}/></Form.Item><Form.Item name={[f.name,'count']} label="节数"><InputNumber min={1} max={8}/></Form.Item><Button onClick={()=>remove(f.name)}>移除</Button></Space>)}<Button onClick={()=>add({day:2,start:1,count:4})}>添加授课日</Button></>}</Form.List>
          <Form.Item name="room_id" label="上课地点（可选，发布前落实）" extra={rooms.length?'可暂不设置；开放填报后仍可在课程表编排页补充地点':'暂无地点，请先在基础数据的教室管理中添加教室或实验室'}><Select placeholder="请选择上课教室或实验室" allowClear options={rooms.map(r=>({value:r.id,label:`${r.name} · ${r.room_type} · ${r.capacity}座`,disabled:!r.is_available}))}/></Form.Item>
          <Form.Item name="profile_verified" valuePropName="checked"><Checkbox>课程方向和领域标签已核对</Checkbox></Form.Item>
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
  return can(user,'teaching')?<TeacherSelectionPage/>:<ManagementPlanningWorkspace/>;
}
