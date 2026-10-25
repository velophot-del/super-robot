import {useCallback,useEffect,useState} from 'react';
import {Alert,Button,Empty,Input,Modal,Space,Table,Tag,message} from 'antd';
import {planningApi} from '../api/planning';
import {formatTeachingSlots} from '../lib/departmentSchedule';

export default function DepartmentScheduleInbox({planId,disabled,onRefresh}:{planId:number;disabled:boolean;onRefresh:()=>void}){
  const [rows,setRows]=useState<any[]>([]),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const load=useCallback(async()=>{setLoading(true);setError('');try{setRows(await planningApi.departmentScheduleReviews(planId));}catch(e){setError(e instanceof Error?e.message:'调剂申请加载失败');}finally{setLoading(false);}},[planId]);
  useEffect(()=>{void load();},[load]);
  const decide=(row:any,approved:boolean)=>{
    let reason=approved?'已核验调剂方案与排课约束':'请按管理员意见调整后重新提交';
    Modal.confirm({title:approved?'确认主任调剂':'退回主任调剂',content:<Input.TextArea aria-label="管理员确认意见" defaultValue={reason} onChange={e=>{reason=e.target.value;}}/>,onOk:async()=>{
      if(!reason.trim()){message.error('请填写处理意见');throw new Error('请填写处理意见');}
      setBusy(true);try{await planningApi.decideDepartmentSchedule(row.plan_id,row.id,{proposal_id:row.proposal_id,approved,reason});message.success(approved?'调剂已写入正式课表':'调剂已退回主任');await load();onRefresh();}catch(e){message.error(e instanceof Error?e.message:'处理失败');throw e;}finally{setBusy(false);}
    }});
  };
  return <div>
    <Space style={{width:'100%',justifyContent:'space-between',marginBottom:8}}><span>主任提交的调剂由管理员复核并最终确认。</span><Button size="small" onClick={()=>void load()}>刷新</Button></Space>
    {error&&<Alert type="error" showIcon title={error} style={{marginBottom:8}}/>}
    <Table<any> rowKey={r=>`${r.plan_id}-${r.id}`} size="small" loading={loading} dataSource={rows} pagination={{pageSize:5}} locale={{emptyText:<Empty description="暂无待确认调剂"/>}} scroll={{x:850}} columns={[
      {title:'周期',dataIndex:'plan_name',width:160},
      {title:'课程 / 班级',render:(_,r)=><><b>{r.name}</b><div>{r.major} · {r.cohort}级 · {r.group}</div></>},
      {title:'教师调整建议',render:(_,r)=><><div>当前：{r.teacher_names?.join('、')||'未分配'} → 建议：{r.proposal_teacher_names?.join('、')||'未指定教师'}</div><div>系统安排：第{r.start_week??'—'}–{r.end_week??'—'}周 · {r.room_name||'未安排教室'} · {formatTeachingSlots(r.slots||[])}</div><Tag color="orange">仅调整教师，待管理员确认</Tag></>},
      {title:'操作',fixed:'right',render:(_,r)=><Space><Button type="primary" size="small" disabled={disabled||busy} onClick={()=>decide(r,true)}>确认并应用</Button><Button danger size="small" disabled={disabled||busy} onClick={()=>decide(r,false)}>退回</Button></Space>},
    ]}/>
  </div>;
}
