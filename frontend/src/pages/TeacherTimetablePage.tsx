import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Button, Card, Empty, Input, Modal, Result, Select, Space, Spin, Table, Tag, Typography, message } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import api from '../api/client';
import { periodKey, timetablePeriods } from '../lib/teacherWorkbench';
import { selectionSlots } from '../lib/selectionGrid';
import StageSelectionTable from '../components/StageSelectionTable';
import { planningApi } from '../api/planning';
import TimetableView from './TimetableView';

export default function TeacherTimetablePage(){
  const {user}=useAuth();
  const [searchParams]=useSearchParams();
  const requestedVersion=searchParams.get('version');
  const [data,setData]=useState<any>(),[selection,setSelection]=useState(''),[loading,setLoading]=useState(true),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  const [exportId,setExportId]=useState<number>(),[exportBusy,setExportBusy]=useState(false);
  const [changeTask,setChangeTask]=useState<any>(),[changeReason,setChangeReason]=useState(''),[desiredChange,setDesiredChange]=useState('');
  const download=async(id:number)=>{
    setExportBusy(true);
    try{const blob=await planningApi.exportPersonal(id);const url=URL.createObjectURL(blob);const anchor=document.createElement('a');anchor.href=url;anchor.download=`我的课表_周期${id}.xlsx`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message.success('个人课表 Excel 已生成');}
    catch(e){message.error(e instanceof Error?e.message:'课表导出失败');}finally{setExportBusy(false);}
  };
  const teaching=can(user,'teaching');
  const refreshData=()=>setRefresh(v=>v+1);
  const confirmTask=async(batch:any,task:any)=>{
    try{await planningApi.confirmSchedule(batch.plan.id,{snapshot_id:batch.snapshot_id,task_id:task.id});message.success('已确认授课安排');refreshData();}
    catch(e){message.error(e instanceof Error?e.message:'确认失败');}
  };
  const submitChange=async()=>{
    if(!changeTask)return;
    try{await planningApi.requestScheduleChange(changeTask.plan_id,{snapshot_id:changeTask.snapshot_id,task_id:changeTask.id,reason:changeReason,desired_change:desiredChange});message.success('调课申请已提交');setChangeTask(undefined);setChangeReason('');setDesiredChange('');refreshData();}
    catch(e){message.error(e instanceof Error?e.message:'提交申请失败');}
  };
  useEffect(()=>{
    let active=true;
    if(!teaching)return;
    setLoading(true);setError('');setData(undefined);
    void api.get('/my/planning-timetable').then((result:any)=>{
      if(!active)return;
      setData(result);
      const keys=[...timetablePeriods(result.batches,result.current_period).map(p=>`period:${periodKey(p)}`),...result.legacy_versions.map((v:string)=>`legacy:${v}`)];
      setSelection(previous=>keys.includes(previous)?previous:requestedVersion&&keys.includes(`legacy:${requestedVersion}`)?`legacy:${requestedVersion}`:`period:${periodKey(result.current_period)}`);
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:'读取个人课表失败');}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[teaching,user?.id,refresh,requestedVersion]);
  if(!teaching)return <Result status="403" title="账号没有教学职能"/>;
  const periods=data?timetablePeriods(data.batches,data.current_period):[];
  const batches=(data?.batches||[]).filter((b:any)=>`period:${periodKey(b.plan)}`===selection);
  const legacy=selection.startsWith('legacy:');
  const rows=batches.flatMap((b:any)=>b.tasks.map((t:any)=>({...t,key:`${b.snapshot_id}-${t.id}`,plan_name:b.plan.name,plan_id:b.plan.id,snapshot_id:b.snapshot_id})));
  return <Space orientation="vertical" style={{width:'100%'}} size="large">
    <Space wrap style={{width:'100%',justifyContent:'space-between'}}><Typography.Title level={3} style={{margin:0}}>我的课表</Typography.Title><Space wrap>
      <Select aria-label="个人课表学期或历史版本" value={selection||undefined} disabled={loading} style={{minWidth:300,maxWidth:'100%'}} onChange={setSelection} options={[
        {label:'已发布个人课表',options:periods.map(p=>({value:`period:${periodKey(p)}`,label:`${p.academic_year}学年 第${p.academic_term===1?'一':'二'}学期${data&&periodKey(p)===periodKey(data.current_period)?'（当前学期）':''}`}))},
        {label:'旧系统历史课表（学期未标注）',options:(data?.legacy_versions||[]).map((v:string)=>({value:`legacy:${v}`,label:`历史版本 ${v}`}))},
      ]}/><Button disabled={loading} onClick={()=>setRefresh(v=>v+1)}>刷新</Button>
    </Space></Space>
    <Space wrap><Typography.Text>导出周期</Typography.Text><Select aria-label="选择个人课表导出周期" placeholder="选择本人有已发布课表的周期" value={exportId} disabled={loading||exportBusy} style={{minWidth:300,maxWidth:'100%'}} onChange={setExportId} options={(data?.batches||[]).map((b:any)=>({value:b.plan.id,label:`${b.plan.academic_year} 第${b.plan.academic_term}学期 · ${b.plan.name}`}))}/><Button type="primary" loading={exportBusy} disabled={exportId===undefined||loading} onClick={()=>exportId!==undefined&&void download(exportId)}>导出个人20周课表 Excel</Button></Space>
    <Typography.Text type="secondary">按20周可视化布局导出，并附课程明细。仅导出所选周期本人已发布的课程，不包含其他教师课程或旧系统未标注学期的历史版本。</Typography.Text>
    {error&&<Alert showIcon type="error" title={error}/>}
    <Spin spinning={loading}>
      {data&&(legacy?<><Alert type="info" showIcon title="旧系统历史版本，未标注学期" description="此处仅展示本人历史课表，不作为当前学期的授课安排。"/><TimetableView key={selection} versionOverride={selection.slice(7)}/></>:batches.length?<Space orientation="vertical" style={{width:'100%'}} size="large">
        <Alert type="info" showIcon title="仅显示管理员已发布的本人课表" description="阶段课表与下方任务明细均取自发布快照；匹配审核中的任务尚未形成正式课表。"/>
        {(data.notifications||[]).length>0&&<Card size="small" title="排课通知"><Space direction="vertical" style={{width:'100%'}}>{data.notifications.map((n:any)=><Alert key={n.id} type={n.kind==='change_request_rejected'?'warning':'info'} showIcon title={n.payload.message}/>)}</Space></Card>}
        {batches.map((batch:any)=><Card key={batch.snapshot_id} title={batch.plan.name}>
          <StageSelectionTable plan={batch.plan} tasks={batch.tasks} selected={[]} disabled readOnly onToggle={()=>{}} onTask={(task)=>Modal.info({title:task.name,content:<Space orientation="vertical"><span>{task.group} · W{task.start_week}—W{task.end_week}</span><span>{selectionSlots(task)}</span><span>地点：{task.room_name||'未注明'}</span></Space>})}/>
        </Card>)}
        <Table rowKey="key" dataSource={rows} pagination={{pageSize:10}} scroll={{x:850}} columns={[
          {title:'课程',dataIndex:'name'},{title:'班级',dataIndex:'group'},{title:'周期',dataIndex:'plan_name'},
          {title:'授课周段',render:(_,t:any)=>`W${t.start_week}—W${t.end_week}`},
          {title:'上课时段',render:(_,t:any)=>selectionSlots(t)},{title:'地点',dataIndex:'room_name'},
          {title:'本人确认',render:(_,t:any)=><Tag color={t.confirmation_status==='confirmed'?'green':'default'}>{t.confirmation_status==='confirmed'?'已确认':'待确认'}</Tag>},
          {title:'调课申请',render:(_,t:any)=>t.change_request?<Tag color={t.change_request.status==='pending'?'orange':t.change_request.status==='approved'?'green':'red'}>{t.change_request.status==='pending'?'处理中':t.change_request.status==='approved'?'已批准':'未批准'}</Tag>:'—'},
          {title:'操作',fixed:'right',render:(_,t:any)=>{const batch=batches.find((b:any)=>b.tasks.some((x:any)=>x.id===t.id));return <Space><Button size="small" disabled={t.confirmation_status==='confirmed'} onClick={()=>batch&&void confirmTask(batch,t)}>确认</Button><Button size="small" disabled={t.change_request?.status==='pending'} onClick={()=>{setChangeTask({...t,plan_id:batch?.plan.id,snapshot_id:batch?.snapshot_id});setChangeReason('');setDesiredChange('');}}>申请调课</Button></Space>;}}
        ]}/>
      </Space>:<Empty description={data&&selection===`period:${periodKey(data.current_period)}`?'当前学期暂无已发布的个人课表，请等待管理员发布':'所选学期暂无已发布的个人课表'}/>)}
    </Spin>
    <Modal title="申请调整课程安排" open={!!changeTask} onCancel={()=>setChangeTask(undefined)} onOk={()=>void submitChange()} okButtonProps={{disabled:changeReason.trim().length<5}}>
      <Space direction="vertical" style={{width:'100%'}}><Typography.Text>{changeTask?.name} · {changeTask?.group}</Typography.Text><Input.TextArea value={changeReason} onChange={e=>setChangeReason(e.target.value)} maxLength={1000} showCount rows={3} placeholder="请说明调课原因（至少5字）"/><Input.TextArea value={desiredChange} onChange={e=>setDesiredChange(e.target.value)} maxLength={1000} showCount rows={2} placeholder="期望调整方式（选填）"/></Space>
    </Modal>
  </Space>;
}
