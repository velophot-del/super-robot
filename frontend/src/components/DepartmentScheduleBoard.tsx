import {useEffect, useState} from 'react';
import {Alert, Button, Card, Empty, Input, Modal, Select, Space, Table, Tabs, Tag, Tooltip, Typography, message} from 'antd';
import {CheckOutlined, EditOutlined, ReloadOutlined} from '@ant-design/icons';
import {planningApi} from '../api/planning';
import {stageLanes} from '../lib/adminStageGrid';
import {reviewRows} from '../lib/reviewRows';
import {departmentScheduleDraft, departmentScheduleEditable, departmentScheduleStatusLabel, formatTeachingSlots} from '../lib/departmentSchedule';

const statusColor:Record<string,string>={pending:'default',draft:'blue',submitted:'orange',approved:'green',returned:'red',stale:'volcano'};
export default function DepartmentScheduleBoard({plan,tasks,busy,onRefresh}:{plan:any;tasks:any[];busy:boolean;onRefresh:()=>void}){
  const [selected,setSelected]=useState<any>();
  const [draft,setDraft]=useState<any>();
  const [options,setOptions]=useState<any>();
  const [loading,setLoading]=useState(false);
  const [loadError,setLoadError]=useState('');
  const [saving,setSaving]=useState(false);
  const [filterMajor,setFilterMajor]=useState<string>();
  const placed=tasks.filter(task=>task.start_week&&task.end_week);
  const groups=reviewRows(placed,plan).filter(([,row])=>!filterMajor||row.major===filterMajor);
  const unplaced=tasks.filter(task=>!task.start_week||!task.end_week);
  const weeks=Number(plan.weeks)||20;
  const teacherRows=tasks.flatMap((task:any)=>(task.applicants||[]).map((applicant:any)=>({...applicant,task,plan_name:task.plan_name||plan.name})))
    .filter((row:any)=>!filterMajor||(row.task.major||row.task.department)===filterMajor);
  const open=(task:any)=>{
    setSelected(task);setDraft(departmentScheduleDraft(task));setOptions(undefined);setLoadError('');
  };
  const selectedId=selected?.id;
  const selectedPlanId=selected?.plan_id||plan.id;

  useEffect(()=>{
    if(!selectedId)return;
    let active=true;setLoading(true);
    void planningApi.reviewTaskOptions(selectedPlanId,selectedId).then(data=>{
      if(!active)return;
      setOptions(data);
      setDraft((current:any)=>current?{...current,teacher_ids:current.teacher_ids?.length?current.teacher_ids:(data.teacher_ids||[])}:current);
    }).catch(error=>{if(active)setLoadError(error instanceof Error?error.message:'教师选项加载失败');})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[selectedId,selectedPlanId]);

  const update=(key:string,value:any)=>setDraft((current:any)=>({...current,[key]:value}));
  const save=async()=>{
    if(!selected||!draft)return;
    if(draft.teacher_ids.length!==Number(selected.teacher_count||1)){
      message.error(`请选择${selected.teacher_count||1}名授课教师`);return;
    }
    setSaving(true);
    try{
      const result:any=await planningApi.saveDepartmentScheduleDraft(selected.plan_id||plan.id,selected.id,{...draft,reason:''});
      await planningApi.submitDepartmentSchedule(selected.plan_id||plan.id,selected.id,result.proposal_id);
      message.success('教师调整已提交管理员确认');
      setSelected(undefined);onRefresh();
      return result.proposal_id as number;
    }catch(error){message.error(error instanceof Error?error.message:'保存调剂草案失败');}
    finally{setSaving(false);}
  };
  const submit=save;
  const reviewApplicant=(applicant:any,approved:boolean)=>{
    let reason=approved?'已核对教师任课资格与负荷':'请补充或调整申报信息';
    Modal.confirm({title:approved?'通过教师课程初审':'退回教师课程申请',
      content:<Input.TextArea aria-label="教师初审意见" defaultValue={reason} onChange={event=>{reason=event.target.value;}}/>,
      onOk:async()=>{
        if(!reason.trim()){message.error('请填写审核意见');throw new Error('请填写审核意见');}
        try{await planningApi.decideDepartmentReview(selected.plan_id||plan.id,{submission_id:applicant.submission_id,task_id:selected.id,approved,reason});message.success('教师初审已保存');onRefresh();}
        catch(error){message.error(error instanceof Error?error.message:'教师初审保存失败');throw error;}
      }});
  };
  const startDate=(cohort:string)=>plan.cohort_calendar_rules?.[String(cohort||'').replace(/(?:级|届)$/,'')]?.start_date||plan.start_date;
  const teacherOptions=(options?.teachers||[]).map((teacher:any)=>({value:teacher.teacher_id,
    label:`${teacher.teacher_name} · ${teacher.review_status==='approved'?'初审通过':teacher.review_status==='pending'?'待初审':teacher.review_status==='returned'?'已退回':'可选择'}${teacher.eligible===false?' · '+(teacher.reasons||[]).join('；'):''}`,
    disabled:!['approved','legacy'].includes(teacher.review_status)||teacher.eligible===false}));
  (options?.teacher_ids||[]).forEach((id:number,index:number)=>{
    if(!teacherOptions.some((item:any)=>item.value===id))teacherOptions.push({value:id,label:`${options.teacher_names?.[index]||`教师${id}`} · 当前分配`,disabled:true});
  });
  const canEdit=selected&&departmentScheduleEditable(selected);

  const scheduleView=<>
    <Space wrap style={{width:'100%',justifyContent:'space-between',marginBottom:12}}>
      <Typography.Text type="secondary">默认显示本室授权专业班级的全部课程；主任仅提出授课教师调整建议，管理员确认后应用教师分配。</Typography.Text>
      <Select aria-label="甘特图专业筛选" allowClear placeholder="全部专业" value={filterMajor} onChange={setFilterMajor}
        options={[...new Set(tasks.map(task=>task.major||task.department).filter(Boolean))].map(value=>({value,label:value}))} style={{width:190}}/>
    </Space>
    {groups.length>0&&<div style={{overflowX:'auto',border:'1px solid #d9d9e3',borderRadius:8}}>
      <table aria-label={`${plan.name}教研室课程甘特图`} style={{borderCollapse:'collapse',width:'100%',minWidth:170+weeks*56}}>
        <colgroup><col style={{width:170}}/>{Array.from({length:weeks},(_,index)=><col key={index} style={{width:56}}/>)}</colgroup>
        <thead><tr style={{background:'#f3f4f6'}}>
          <th style={{border:'1px solid #d9d9e3',padding:8,textAlign:'left'}}>专业 / 届次 / 班级</th>
          {Array.from({length:weeks},(_,index)=><th key={index} style={{border:'1px solid #d9d9e3',padding:'5px 2px',fontSize:12}}>第{index+1}周</th>)}
        </tr></thead>
        <tbody>{groups.map(([key,group])=>{
          const bars=stageLanes(group.tasks);const height=Math.max(100,...bars.map(bar=>(bar.lane+1)*92));
          return <tr key={key}>
            <th style={{border:'1px solid #d9d9e3',padding:8,textAlign:'left',verticalAlign:'top'}}>
              <div>{group.major}</div><Typography.Text type="secondary">{group.cohort?`${group.cohort}级 · `:''}{group.group}</Typography.Text>
              <div style={{fontSize:11,color:'#64748d'}}>第1周周一 {startDate(group.cohort)}</div>
            </th>
            <td colSpan={weeks} style={{border:'1px solid #d9d9e3',padding:0}}>
              <div style={{position:'relative',height}}>
                {Array.from({length:weeks},(_,index)=><div key={index} style={{position:'absolute',left:`${index*100/weeks}%`,width:`${100/weeks}%`,height:'100%',borderRight:'1px solid #eee'}}/>)}
                {bars.map(({task,lane})=>{
                  const status=task.department_schedule_status||'pending';
                  return <div key={task.id} style={{position:'absolute',left:`${(task.start_week-1)*100/weeks}%`,width:`${(task.end_week-task.start_week+1)*100/weeks}%`,top:lane*92+4,height:84,overflow:'hidden',zIndex:1,boxSizing:'border-box',padding:5,borderRadius:6,border:'1px solid #9eb7cf',background:'#f5f8fc'}}>
                    <Tooltip title={`${task.name} · ${task.start_week}-${task.end_week}周`}><Button type="link" disabled={busy} onClick={()=>open(task)} style={{padding:0,height:22,fontWeight:600,width:'100%',textAlign:'left',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{task.name}</Button></Tooltip>
                    <div style={{fontSize:11,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{task.teacher_names?.join('、')||'待定教师'} · {task.room_name||'待定教室'}</div>
                    <Tag color={statusColor[status]}>{departmentScheduleStatusLabel(status)}</Tag>
                    <Button size="small" type="text" aria-label={`调剂${task.name}`} icon={<EditOutlined/>} disabled={busy||!departmentScheduleEditable(task)} onClick={()=>open(task)}/>
                  </div>;
                })}
              </div>
            </td>
          </tr>;
        })}</tbody>
      </table>
    </div>}
    {unplaced.length>0&&<Card size="small" title={`待安排课程 · ${unplaced.length}门`} style={{marginTop:12}}>
      <Space wrap>{unplaced.map(task=><Card key={task.id} size="small" style={{width:260}}>
        <Typography.Text strong>{task.name}</Typography.Text><div>{task.major||task.department} · {task.cohort}级 · {task.group}</div>
        <Tag color={statusColor[task.department_schedule_status||'pending']}>{departmentScheduleStatusLabel(task.department_schedule_status||'pending')}</Tag>
        <Button size="small" type="link" disabled={!departmentScheduleEditable(task)} onClick={()=>open(task)}>调整授课教师</Button>
      </Card>)}</Space>
    </Card>}
    {!groups.length&&!unplaced.length&&<Empty description="当前周期没有本教研室授权专业的课程"/>}

    <Modal title={selected?`课程审核与教师调整 · ${selected.name}`:'课程审核与教师调整'} open={Boolean(selected)} onCancel={()=>setSelected(undefined)} footer={null} width={760} destroyOnHidden>
      {selected&&draft&&<Space direction="vertical" style={{width:'100%'}} size="middle">
        <Alert type="info" showIcon title="主任仅建议授课教师；周段、教室和周内节次按系统课表数据生成，管理员确认前正式安排不变。"/>
        {loadError&&<Alert type="error" showIcon title={loadError} action={<Button icon={<ReloadOutlined/>} onClick={()=>{setSelected({...selected});setLoadError('');}}>重试</Button>}/>}
        <Typography.Text type="secondary">{selected.plan_name||plan.name} · {selected.group} · {selected.program_semester?`培养第${selected.program_semester}学期`:''}</Typography.Text>
        <label>建议教师 <Select mode="multiple" aria-label="课程建议教师" value={draft.teacher_ids} onChange={value=>update('teacher_ids',value)} loading={loading} disabled={loading||Boolean(loadError)||!canEdit} options={teacherOptions} style={{width:'100%'}} placeholder="从本室已申报且初审通过的教师中选择"/></label>
        <div style={{padding:12,background:'#f7f8fa',borderRadius:6}}><Typography.Text strong>系统生成的课程安排（只读）</Typography.Text>
          <div>周段：{selected.start_week&&selected.end_week?`第${selected.start_week}–${selected.end_week}周`:'待系统安排'}</div>
          <div>教室：{selected.room_name||'待系统安排'}</div>
          <div>周内节次：{formatTeachingSlots(selected.slots||[])}</div>
        </div>
        {!!(selected.applicants||[]).length&&<div><Typography.Text strong>教师课程申报初审</Typography.Text>
          <Table size="small" pagination={false} rowKey="submission_id" dataSource={selected.applicants} columns={[
            {title:'教师',dataIndex:'teacher_name'},
            {title:'状态',dataIndex:'review_status',render:(value:string)=><Tag color={value==='approved'?'green':value==='returned'?'red':value==='pending'?'orange':'default'}>{value==='approved'?'已通过':value==='returned'?'已退回':value==='pending'?'待初审':'原流程'}</Tag>},
            {title:'操作',render:(_:unknown,applicant:any)=><Space><Button size="small" type="primary" disabled={!canEdit||!['pending','returned'].includes(applicant.review_status)} onClick={()=>reviewApplicant(applicant,true)}>通过</Button><Button size="small" danger disabled={!canEdit||!['pending','returned'].includes(applicant.review_status)} onClick={()=>reviewApplicant(applicant,false)}>退回</Button></Space>},
          ]}/>
        </div>}
        {selected.department_schedule_status==='submitted'&&<Alert type="warning" title="已送管理员确认，当前版本不能继续修改"/>}
        {!selected.can_edit_department_schedule&&<Alert type="info" title="该课程属于其他教研室，当前仅供查看"/>}
        <Space style={{justifyContent:'flex-end',width:'100%'}}>
          <Button onClick={()=>setSelected(undefined)}>关闭</Button>
          {canEdit&&<Button type="primary" icon={<CheckOutlined/>} loading={saving} onClick={()=>void submit()}>提交教师调整</Button>}
        </Space>
      </Space>}
    </Modal>
  </>;
  const teacherView=<Table<any> size="small" rowKey={(row:any)=>`${row.submission_id}-${row.task.id}`} dataSource={teacherRows} pagination={{pageSize:8}} locale={{emptyText:<Empty description="本教研室暂无教师选课记录"/>}} columns={[
    {title:'教师',dataIndex:'teacher_name',width:130},
    {title:'选课课程',render:(_:unknown,row:any)=><><b>{row.task.name}</b><div>{row.task.major||row.task.department} · {row.task.cohort}级 · {row.task.group}</div></>},
    {title:'周期 / 周段',render:(_:unknown,row:any)=><>{row.plan_name}<div>第{row.task.start_week||'—'}–{row.task.end_week||'—'}周</div></>},
    {title:'审核状态',dataIndex:'review_status',render:(value:string)=><Tag color={value==='approved'?'green':value==='returned'?'red':value==='pending'?'orange':'default'}>{value==='approved'?'已通过':value==='returned'?'已退回':value==='pending'?'待审核':'原流程'}</Tag>},
    {title:'审核',render:(_:unknown,row:any)=><Space><Button size="small" type="primary" disabled={busy||!row.selected||!['pending','returned'].includes(row.review_status)} onClick={()=>{setSelected(row.task);reviewApplicant(row,true);}}>通过</Button><Button size="small" danger disabled={busy||!row.selected||!['pending','returned'].includes(row.review_status)} onClick={()=>{setSelected(row.task);reviewApplicant(row,false);}}>退回</Button></Space>},
    {title:'教师调整',render:(_:unknown,row:any)=><Button size="small" disabled={!row.selected||busy||!departmentScheduleEditable(row.task)} onClick={()=>open(row.task)}>修改课程教师</Button>},
  ]}/>;
  return <Tabs defaultActiveKey="teachers" items={[{key:'teachers',label:`教师选课 · ${teacherRows.length}`,children:teacherView},{key:'schedule',label:'课程甘特图',children:scheduleView}]}/>;
}
