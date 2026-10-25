import { useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Empty, Modal, Select, Space, Table, Tag, Tooltip, Typography, message } from 'antd';
import { EditOutlined, EnvironmentOutlined, ReloadOutlined } from '@ant-design/icons';
import { weekDates } from '../lib/selectionGrid';
import { stageLanes } from '../lib/adminStageGrid';
import { reviewRows } from '../lib/reviewRows';
import {departmentDirectAssign,departmentScheduleEditable,departmentScheduleStatusLabel,formatTeachingSlots} from '../lib/departmentSchedule';
import { planningApi } from '../api/planning';

type Props = {
  plan: any;
  tasks: any[];
  match: any;
  busy: boolean;
  canAssign: boolean;
  reason: string;
  onAssign: (task: any, teacherIds: number[]) => void;
  onRoom: (task:any,roomId:number|null)=>void;
  admin: boolean;
  onReviewed?:()=>void;
};

const WEEK_WIDTH = 56;
const GROUP_WIDTH = 160;
const CARD_HEIGHT = 120;
const LANE_HEIGHT = 130;

export default function ReviewTimetable({ plan, tasks, match, busy, canAssign, reason, onAssign, onRoom, admin, onReviewed }: Props) {
  const [reviewing,setReviewing]=useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [value, setValue] = useState<number[]>([]);
  const [roomTask,setRoomTask]=useState<any>(null);
  const [roomId,setRoomId]=useState<number|null>(null);
  const [resourceOptions,setResourceOptions]=useState<any>();
  const [resourceLoading,setResourceLoading]=useState(false);
  const [resourceError,setResourceError]=useState('');
  const [resourceRetry,setResourceRetry]=useState(0);
  const [majorFilter,setMajorFilter]=useState<string>();
  const [cohortFilter,setCohortFilter]=useState<string>();
  const resourceTask=roomTask||editing;
  const resourcePlanId=resourceTask?.plan_id||plan.id;
  const resourceTaskId=resourceTask?.id;
  useEffect(()=>{
    let active=true;setResourceOptions(undefined);setResourceError('');
    if(!resourceTaskId){setResourceLoading(false);return;}
    setResourceLoading(true);
    void planningApi.reviewTaskOptions(resourcePlanId,resourceTaskId).then(data=>{
      if(!active)return;setResourceOptions(data);setValue(data.teacher_ids||[]);
    }).catch(e=>{if(active)setResourceError(e instanceof Error?e.message:'教师及上课地点加载失败');})
      .finally(()=>{if(active)setResourceLoading(false);});
    return()=>{active=false;};
  },[resourcePlanId,resourceTaskId,resourceRetry]);
  const weeks = Number(plan.weeks) || 20;
  const placed = tasks.filter(task => task.start_week && task.end_week);
  const allRows = reviewRows(placed,plan);
  const rows=allRows.filter(([,row])=>(!majorFilter||row.major===majorFilter)&&(!cohortFilter||row.cohort===cohortFilter));
  const cohortStart=(cohort:string)=>plan.cohort_calendar_rules?.[String(cohort||'').replace(/(?:级|届)$/,'')]?.start_date||plan.start_date;
  const startDates=new Set(rows.map(([,group])=>cohortStart(group.cohort)));
  const candidatesFor = (task: any) => (match?.candidates || []).filter((candidate: any) => candidate.task_id === task.id);

  useEffect(() => { if (editing) setValue(editing.teacher_ids || []); }, [editing]);
  const open = (task: any) => { setEditing(task); setValue(task.teacher_ids || []); };
  const applicants = resourceOptions?.teachers || [];
  const options: { value: number; label: string; disabled: boolean }[] = applicants.map((applicant: any) => {
    const candidate = applicant.eligible!=null?applicant:candidatesFor(editing).find((item: any) => item.teacher_id === applicant.teacher_id);
    return {
      value: applicant.teacher_id,
      label: candidate
        ? `${applicant.teacher_name} · ${applicant.review_status==='unsubmitted'?'未申报，可人工指定':applicant.review_status==='pending'?'已申报待初审':applicant.review_status==='returned'?'申报已退回':candidate.eligible ? '可分配' : (candidate.reasons || []).join('；') || '不符合条件'}${candidate.normalized_total != null ? ` · ${candidate.normalized_total}%` : ''}`
        : applicant.teacher_name,
      disabled: Boolean(candidate && !candidate.eligible),
    };
  });
  // 兼容历史任务：当前已分配教师即使不在本批次申报列表中，也要能正常显示。
  (resourceOptions?.teacher_ids || []).forEach((teacherId: number, index: number) => {
    if (!options.some(option => option.value === teacherId)) {
      options.push({ value: teacherId, label: resourceOptions.teacher_names?.[index] || `教师${teacherId}`, disabled: true });
    }
  });
  const current = resourceOptions?.teacher_names?.length ? resourceOptions.teacher_names.join('、') : editing?.teacher_names?.join('、')||'待审核';
  const directAssign = !admin && (typeof resourceOptions?.can_direct_assign === 'boolean'
    ? resourceOptions.can_direct_assign
    : departmentDirectAssign(editing||{}));
  const canSave = !reviewing && (admin||departmentScheduleEditable(editing||{})) && canAssign && resourceOptions?.can_assign && !resourceLoading && !resourceError && !busy && applicants.length > 0 && value.length === editing?.teacher_count && value.every(id=>options.some(option=>option.value===id&&!option.disabled)) && (!admin||Boolean(reason.trim()));
  const resourceErrorView=resourceError?<Alert type="error" showIcon title={`教师及上课地点加载失败：${resourceError}`} action={<Button size="small" icon={<ReloadOutlined/>} onClick={()=>setResourceRetry(v=>v+1)}>重试</Button>} style={{marginBottom:12}}/>:null;
  const reviewApplicant=async(applicant:any,approved:boolean)=>{
    setReviewing(true);
    try{
      await planningApi.decideDepartmentReview(resourcePlanId,{submission_id:applicant.submission_id,task_id:editing.id,approved,reason:approved?'已核对任课资格与负荷':'请调整选课后重新提交'});
      setResourceRetry(v=>v+1);onReviewed?.();message.success(approved?'申请已通过':'申请已退回');
    }catch(error){message.error(error instanceof Error?error.message:'审核失败');}
    finally{setReviewing(false);}
  };
  const save = () => {
    if (!editing || !canSave) return;
    onAssign({...editing,match_id:resourceOptions.match_id,has_applications:resourceOptions.has_applications,can_direct_assign:resourceOptions.can_direct_assign,base_revision:resourceOptions.base_revision,base_fingerprint:resourceOptions.base_fingerprint}, value);
    setEditing(null);
  };

  if (!placed.length) return <Empty description="暂无已排周段的课程任务，配置周段后可在此人工调剂" />;
  return <>
    <div style={{display:'flex',gap:8,marginBottom:12}}>
      <Select aria-label="审核年级" allowClear placeholder="全部年级" value={cohortFilter} onChange={setCohortFilter} style={{width:150}} options={[...new Set(allRows.map(([,row])=>row.cohort))].filter(Boolean).map(value=>({value,label:`${value}级`}))}/>
      <Select aria-label="审核专业" allowClear placeholder="全部专业" value={majorFilter} onChange={setMajorFilter} style={{width:200}} options={[...new Set(allRows.map(([,row])=>row.major))].map(value=>({value,label:value}))}/>
    </div>
    <div style={{ overflowX: 'auto', border: '1px solid #d9d9e3', borderRadius: 8 }}>
      <table aria-label={admin?"全学院实时课表":"本教研室实时课表"} style={{ borderCollapse: 'collapse', width: '100%', minWidth: GROUP_WIDTH + weeks * WEEK_WIDTH, tableLayout: 'fixed' }}>
        <colgroup><col style={{ width: GROUP_WIDTH }} />{Array.from({ length: weeks }, (_, index) => <col key={index} style={{ width: WEEK_WIDTH }} />)}</colgroup>
        <thead><tr style={{ background: '#f3f4f6' }}>
          <th style={{ border: '1px solid #d9d9e3', padding: 6, position:'sticky',left:0,zIndex:2,background:'#f3f4f6' }}>专业 / 年级 / 教学组</th>
          {Array.from({ length: weeks }, (_, index) => <th key={index} style={{ border: '1px solid #d9d9e3', padding: '5px 2px', fontSize: 12 }}>
            第{index + 1}周<div style={{ fontWeight: 400, fontSize: 10, lineHeight:'14px' }}>{startDates.size===1?weekDates([...startDates][0],index+1).split('—').map((label,i)=><div key={i}>{label}{i===0?'—':''}</div>):'按年级设置'}</div>
          </th>)}
        </tr></thead>
        <tbody>{rows.map(([key, group]) => {
          const bars = stageLanes(group.tasks);
          const height = Math.max(LANE_HEIGHT, ...bars.map(bar => (bar.lane + 1) * LANE_HEIGHT));
          return <tr key={key}>
            <th style={{ border: '1px solid #d9d9e3', padding: 6, textAlign: 'left', verticalAlign: 'top',position:'sticky',left:0,zIndex:2,background:'#fff',overflowWrap:'anywhere' }}>
              <div>{group.major}</div>
              <Typography.Text type="secondary">{group.cohort ? `${group.cohort}级 · ` : ''}{group.group}</Typography.Text>
              <div style={{fontSize:11,color:'#64748d'}}>第1教学周周一 {cohortStart(group.cohort)}</div>
            </th>
            <td colSpan={weeks} style={{ border: '1px solid #d9d9e3', padding: 0 }}>
              <div style={{ position: 'relative', height }}>
                {Array.from({ length: weeks }, (_, index) => <div key={index} style={{ position: 'absolute', left: `${index * 100 / weeks}%`, width: `${100 / weeks}%`, height: '100%', borderRight: '1px solid #eee' }} />)}
                {bars.map(({ task, lane }) => {
                  const names = (task.applicants || []).map((applicant: any) => applicant.teacher_name).join('、') || '暂无';
                  const assigned = task.teacher_names?.length ? task.teacher_names.join('、') : '待审核';
                  const left = `${(task.start_week - 1) * 100 / weeks}%`;
                  const width = `${(task.end_week - task.start_week + 1) * 100 / weeks}%`;
                  return <div key={task.id} style={{
                    position: 'absolute', left, width, top: lane * LANE_HEIGHT + 5, height: CARD_HEIGHT,
                    background: task.locked ? '#edf3fa' : '#fff7e8', border: `1px solid ${task.locked ? '#b5c5d8' : '#f0b35b'}`,
                    borderRadius: 6, padding: 4, boxSizing: 'border-box', overflow: 'hidden', zIndex: 1,
                  }}>
                    <Tooltip title={`${task.name} · ${task.plan_name||plan.name} · W${task.start_week}—W${task.end_week}`}>
                      <Button type="link" onClick={()=>open(task)} style={{padding:0,display:'block',width:'100%',textAlign:'left',height:22,fontSize:14,fontWeight:600,overflow:'hidden'}}><span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',display:'block'}}>{task.name}</span></Button>
                    </Tooltip>
                    <Tooltip title={assigned}><div style={{fontSize:13,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{assigned}</div></Tooltip>
                    <Tooltip title={task.room_address||task.room_name||'未分配教室'}><div style={{fontSize:12,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{task.room_name||'未分配教室'}</div></Tooltip>
                    <Tooltip title={`申报：${names}；需${task.teacher_count}名教师${task.other_applicant_count?`；另有${task.other_applicant_count}名其他教研室教师申报`:''}。${(task.department_recommendations||[]).map((r:any)=>`教研室建议：${r.teacher_names.join('、')}，${r.reason}`).join('；')}`}>
                      <div style={{fontSize:12,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>申报 {task.applicant_count ?? task.applicants?.length ?? 0}人 · {admin?(task.locked?'已确认':'待确认'):task.locked&&(!task.department_schedule_status||task.department_schedule_status==='pending')?'已指定教师':departmentScheduleStatusLabel(task.department_schedule_status)}</div>
                    </Tooltip>
                    <Tooltip title={admin?'分配课程教师':'分配本室教师'}><Button size="small" type="text" style={{width:22,minWidth:22,height:22,padding:0}} aria-label={admin?'分配课程教师':'分配本室教师'} icon={<EditOutlined />} disabled={!canAssign || (admin?!['open','matched'].includes(task.plan_state||plan.state):!departmentScheduleEditable(task))} onClick={() => open(task)}/></Tooltip>
                    {admin&&<Tooltip title="上课地点"><Button size="small" type="text" style={{width:22,minWidth:22,height:22,padding:0}} aria-label="上课地点" icon={<EnvironmentOutlined/>} disabled={busy||task.plan_state==='published'} onClick={()=>{setRoomTask(task);setRoomId(task.room_id??null);}}/></Tooltip>}
                  </div>;
                })}
              </div>
            </td>
          </tr>;
        })}</tbody>
      </table>
    </div>

    <Modal title={roomTask?`上课地点 · ${roomTask.name}`:'上课地点'} open={Boolean(roomTask)} onCancel={()=>setRoomTask(null)} onOk={()=>{onRoom(roomTask,roomId);setRoomTask(null);}} confirmLoading={busy} okButtonProps={{disabled:resourceLoading||Boolean(resourceError)||!resourceOptions?.can_edit_room}}>
      {resourceErrorView}
      {!resourceLoading&&!resourceError&&resourceOptions&&!resourceOptions.can_edit_room&&<Alert type="warning" showIcon title="此课程需跨教研室协调或本人回避，请交学院调整地点" style={{marginBottom:12}}/>}
      <Select aria-label="审核上课地点" loading={resourceLoading} disabled={resourceLoading||Boolean(resourceError)||!resourceOptions?.can_edit_room} allowClear value={roomId} onChange={v=>setRoomId(v??null)} style={{width:'100%'}} options={(resourceOptions?.rooms||[]).map((r:any)=>({value:r.id,label:`${r.name} · ${r.building||''} · ${r.capacity}人`,disabled:r.is_available===false}))}/>
    </Modal>
    <Modal title={editing ? `${admin?'人工调剂':directAssign?'教师分配':'教师选课审核与调整'} · ${editing.name}` : '任课教师'} open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={save}
      okText={admin?'保存调剂':directAssign?'直接分配教师':'提交管理员确认'} confirmLoading={busy} okButtonProps={{ disabled: !canSave }} width={520}>
      {editing && <>
        {resourceErrorView}
        {!admin&&directAssign&&<Alert type="info" showIcon title="该课程暂无教师申报，主任可直接分配本室教师，保存后立即生效。" style={{marginBottom:12}}/>}
        <Descriptions size="small" column={1} bordered items={[
          { key: 'group', label: '教学组', children: editing.group },
          { key: 'weeks', label: '授课周段', children: `W${editing.start_week}—W${editing.end_week}` },
          { key: 'room', label: '系统安排地点', children: editing.room_name||'待安排' },
          { key: 'slots', label: '系统安排节次', children: formatTeachingSlots(editing.slots||[]) },
          { key: 'applicants', label: '申报教师', children: (editing.applicants||[]).map((item:any)=>item.teacher_name).join('、')||'暂无教师申报，可直接指定教师' },
          { key: 'current', label: '当前教师', children: current },
        ]} style={{ marginBottom: 16 }} />
        {!resourceLoading&&!resourceError&&resourceOptions&&applicants.length>0&&!resourceOptions.can_assign&&<Alert type="warning" showIcon title={admin?'当前课程需本人回避或不处于可分配阶段':'当前课程需本人回避或尚未启用两级审核'} style={{marginBottom:12}}/>}
        {!resourceLoading&&!resourceError&&resourceOptions&&!applicants.length&&<Alert type="info" title="当前范围内没有可分配的教师" style={{marginBottom:12}}/>}
        {!admin&&Boolean(editing.applicants?.length)&&<Table<any> size="small" pagination={false} rowKey="submission_id" dataSource={(editing.applicants||[]).filter((applicant:any)=>applicant.selected!==false)} columns={[
          {title:'申报教师',dataIndex:'teacher_name'},
          {title:'审核状态',render:(_,row)=>{const status=applicants.find((item:any)=>item.teacher_id===row.teacher_id)?.review_status||row.review_status;return <Tag>{status==='approved'?'已通过':status==='returned'?'已退回':'待审核'}</Tag>;}},
          {title:'审核',render:(_,row)=><Space><Button size="small" disabled={reviewing||resourceLoading||Boolean(resourceError)||!resourceOptions?.can_assign} onClick={()=>void reviewApplicant(row,true)}>通过</Button><Button size="small" danger disabled={reviewing||resourceLoading||Boolean(resourceError)||!resourceOptions?.can_assign} onClick={()=>void reviewApplicant(row,false)}>退回</Button></Space>},
        ]} style={{marginBottom:16}}/>}
        <Select mode="multiple" showSearch optionFilterProp="label" aria-label="人工调剂教师" value={value} onChange={values => {
          if (values.length > editing.teacher_count) { message.warning(`最多选择 ${editing.teacher_count} 名教师`); return; }
          setValue(values);
        }} options={options} loading={resourceLoading} style={{ width: '100%' }} placeholder={admin?`请选择 ${editing.teacher_count} 名教师`:`请选择 ${editing.teacher_count} 名本室教师`} disabled={!canAssign || !resourceOptions?.can_assign || resourceLoading || Boolean(resourceError) || !applicants.length} />
        <Typography.Paragraph type="secondary" style={{ margin: '10px 0 0', fontSize: 12 }}>
          {admin?`需选择 ${editing.teacher_count} 名教师，填写上方调剂说明后保存。`
            :directAssign?`该课程暂无教师申报，可由主任直接分配 ${editing.teacher_count} 名本室教师，保存后立即写入任课安排。`
            :`请选择 ${editing.teacher_count} 名本室教师，无需申报或填写理由，提交管理员最终确认。`}人工分配不要求教师申报，保存时校验授课负荷与冲突。
        </Typography.Paragraph>
      </>}
    </Modal>
  </>;
}
