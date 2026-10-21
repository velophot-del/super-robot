import { useEffect, useState } from 'react';
import { Alert, Button, Empty, Result, Space, Spin, Table, Tag, Typography } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { can } from '../lib/accessPolicy';
import { planningApi } from '../api/planning';

export default function TeacherMatchPage(){
  const {user}=useAuth();
  const [plans,setPlans]=useState<any[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
  const teaching=can(user,'teaching');
  useEffect(()=>{
    let active=true;
    if(!teaching)return;
    setLoading(true);setError('');setPlans([]);
    void (async()=>{
      try{
        const list:any=await planningApi.plans();
        const results=await Promise.allSettled(list.map((p:any)=>planningApi.state(p.id)));
        if(!active)return;
        setPlans(results.filter((r):r is PromiseFulfilledResult<any>=>r.status==='fulfilled').map(r=>r.value));
        if(results.some(r=>r.status==='rejected'))setError('部分周期读取失败，结果可能不完整，请刷新重试。');
      }catch(e){if(active)setError(e instanceof Error?e.message:'读取匹配结果失败');}
      finally{if(active)setLoading(false);}
    })();
    return()=>{active=false;};
  },[teaching,user?.id,refresh]);
  if(!teaching)return <Result status="403" title="账号没有教学职能"/>;
  const rows=plans.flatMap(plan=>(plan.match?.candidates||[]).filter((c:any)=>c.teacher_id===user?.teacher_id).map((c:any)=>({
    ...c,maximum:c.maximum??plan.match?.maximum,key:`${plan.id}-${c.task_id}`,plan_name:plan.name,state:plan.state,
    task_name:plan.tasks.find((t:any)=>t.id===c.task_id)?.name,
    group:plan.tasks.find((t:any)=>t.id===c.task_id)?.group,
  })));
  return <Space orientation="vertical" style={{width:'100%'}} size="large">
    <Space wrap style={{width:'100%',justifyContent:'space-between'}}><Typography.Title level={3} style={{margin:0}}>我的匹配结果</Typography.Title><Button onClick={()=>setRefresh(v=>v+1)} disabled={loading}>刷新</Button></Space>
    <Typography.Text type="secondary">显示各周期的本人匹配评分；正式授课安排请查看“我的课表”中的已发布课表。</Typography.Text>
    {error&&<Alert type="error" showIcon title={error}/>}
    <Spin spinning={loading}><Table rowKey="key" dataSource={rows} locale={{emptyText:<Empty description="暂无本人匹配结果，请等待管理员运行匹配"/>}} pagination={{pageSize:10}} scroll={{x:1000}} columns={[
      {title:'课程',dataIndex:'task_name'},{title:'班级',dataIndex:'group'},{title:'周期',dataIndex:'plan_name'},
      {title:'周期状态',render:(_,r:any)=><Tag>{r.state==='published'?'已发布':'匹配审核中'}</Tag>},
      {title:'专业匹配度',render:(_,r:any)=>r.professional_fit==null?'资料不足':`${r.professional_fit}%`},
      {title:'擅长课程',render:(_,r:any)=>r.skilled_course_match?'命中':'未命中'},
      {title:'综合分',render:(_,r:any)=>r.raw_total==null?'未知':`${r.raw_total}/${r.maximum??95}`},{title:'说明',dataIndex:'explanation'},
    ]}/></Spin>
  </Space>;
}
