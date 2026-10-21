import { useEffect, useState } from 'react';
import { Alert, Button, Empty, Modal, Select, Space, Spin, Typography, message } from 'antd';
import { useSearchParams } from 'react-router-dom';
import api, { scheduleApi } from '../api/client';
import StageSelectionTable from '../components/StageSelectionTable';
import { selectionSlots } from '../lib/selectionGrid';

export default function AdminHistoryPage(){
  const [exporting,setExporting]=useState(false);
  const download=async(id:number,weeks=20)=>{
    setExporting(true);
    try{const blob=await api.get<Blob>(`/planning/exports/college/${id}`,{responseType:'blob'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`全学院${weeks}周课表_周期${id}.xlsx`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message.success(`全学院${weeks}周课表已导出`);}
    catch(e){message.error(e instanceof Error?e.message:'导出失败');}finally{setExporting(false);}
  };
  const [params]=useSearchParams();
  const requested=params.get('version');
  const [batches,setBatches]=useState<any[]>([]),[versions,setVersions]=useState<any[]>([]);
  const [selection,setSelection]=useState(''),[entries,setEntries]=useState<any[]>([]);
  const [loading,setLoading]=useState(true),[entryLoading,setEntryLoading]=useState(false),[error,setError]=useState(''),[entryError,setEntryError]=useState(''),[refresh,setRefresh]=useState(0);
  const [view,setView]=useState('class_name'),[group,setGroup]=useState<string>();
  useEffect(()=>{
    let active=true;setLoading(true);setError('');
    void Promise.all([api.get('/planning/history/published'),scheduleApi.getVersions()]).then(([history,legacy]:any)=>{
      if(!active)return;setBatches(history);setVersions(legacy);
      const keys=[...history.map((b:any)=>`plan:${b.plan.id}`),...legacy.map((v:any)=>`legacy:${v.version}`)];
      setSelection(old=>keys.includes(old)?old:requested&&keys.includes(`legacy:${requested}`)?`legacy:${requested}`:keys[0]||'');
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:'读取历史课表失败');}).finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[refresh,requested]);
  useEffect(()=>{
    let active=true;setEntries([]);setEntryError('');setGroup(undefined);
    if(!selection.startsWith('legacy:')){setEntryLoading(false);return;}
    setEntryLoading(true);
    void (async()=>{
      const all:any[]=[];
      for(let skip=0;;skip+=2000){
        const page:any=await scheduleApi.list({version:selection.slice(7),skip,limit:2000});
        if(!active)return;all.push(...page);if(page.length<2000)break;
      }
      if(active)setEntries(all);
    })().catch(e=>{if(active)setEntryError(e instanceof Error?e.message:'读取历史版本失败');}).finally(()=>{if(active)setEntryLoading(false);});
    return()=>{active=false;};
  },[selection,refresh]);
  const batch=batches.find(b=>`plan:${b.plan.id}`===selection);
  const coverage=batch?batches.filter(b=>b.plan.start_date===batch.plan.start_date&&b.plan.weeks===batch.plan.weeks):[];
  const legacy=selection.startsWith('legacy:');
  const groups=[...new Set(entries.map(e=>e[view]||'未注明'))].sort();
  const selectedGroup=group||groups[0];
  return <Space orientation="vertical" size="large" style={{width:'100%'}}>
    <Typography.Title level={3}>历史课表</Typography.Title>
    <Space wrap><Select aria-label="历史课表周期或版本" placeholder="选择已发布周期或历史版本" style={{minWidth:320}} value={selection||undefined} onChange={setSelection} options={[
      {label:'已发布排课周期',options:batches.map(b=>({value:`plan:${b.plan.id}`,label:b.plan.name}))},
      {label:'旧系统历史版本',options:versions.map(v=>({value:`legacy:${v.version}`,label:v.version}))},
    ]}/><Button onClick={()=>setRefresh(n=>n+1)}>刷新</Button></Space>
    {batch&&<Alert type="info" showIcon title={`全学院导出范围：${coverage.length}个已发布计划，${coverage.reduce((n,b)=>n+b.tasks.length,0)}项课程任务`} description={<Space orientation="vertical"><span>汇总起始日期 {batch.plan.start_date}、周期 {batch.plan.weeks} 周的所有专业及年级；未发布计划不包含在内。</span><span>{coverage.map(b=>b.plan.name).join('；')}</span><Button type="primary" loading={exporting} disabled={loading||!!error} onClick={()=>void download(batch.plan.id,batch.plan.weeks||20)}>导出全学院{batch.plan.weeks||20}周课表 Excel</Button></Space>}/>}
    <Typography.Text type="secondary">完整展示第1—{batch?.plan.weeks||20}周，空周保留；考试周按年级设置（灰色单元格为考试周）。已发布周期读取正式发布快照。</Typography.Text>
    {(error||entryError)&&<Alert type="error" showIcon title={error||entryError}/>}
    <Spin spinning={loading||entryLoading}>
      {batch?<StageSelectionTable plan={batch.plan} tasks={batch.tasks} selected={[]} disabled readOnly onToggle={()=>{}} onTask={task=>Modal.info({title:task.name,content:<Space orientation="vertical"><span>{task.group} · 第{task.start_week}—{task.end_week}周</span><span>{selectionSlots(task)}</span><span>教师：{task.teacher_names?.join('、')||'未注明'}</span><span>地点：{task.room_name||'未注明'}</span></Space>})}/>:legacy?<>
        <Space wrap style={{marginBottom:16}}><Select aria-label="历史课表查看维度" value={view} onChange={v=>{setView(v);setGroup(undefined);}} options={[{value:'class_name',label:'按班级'},{value:'teacher_name',label:'按教师'},{value:'classroom_name',label:'按教室'}]}/><Select aria-label="历史课表分组" value={selectedGroup} onChange={setGroup} style={{minWidth:180}} options={groups.map(g=>({value:g,label:g}))}/></Space>
        <div style={{overflowX:'auto'}}><table aria-label="历史版本20周课表" style={{borderCollapse:'collapse',minWidth:2600,width:'100%'}}><thead><tr>{Array.from({length:20},(_,i)=><th key={i} style={{border:'1px solid #ddd',padding:8}}>第{i+1}周{i===19?'（考试）':''}</th>)}</tr></thead><tbody><tr>{Array.from({length:20},(_,i)=><td key={i} style={{border:'1px solid #ddd',verticalAlign:'top',padding:8,width:130}}>{entries.filter(e=>(e[view]||'未注明')===selectedGroup&&e.week_number===i+1).map(e=><div key={e.id} style={{padding:6,marginBottom:8,background:'#f5f3ff',borderRadius:4}}><strong>{e.course_name}</strong><div>{e.class_name}</div><div>周{'一二三四五六日'[e.day_of_week-1]} 第{e.period_start}—{e.period_end}节</div><div>{e.teacher_name} · {e.classroom_name}</div></div>)}</td>)}</tr></tbody></table></div>
        {!entryLoading&&!entries.length&&<Empty description="该历史版本暂无课程"/>}
      </>:!loading&&<Empty description="暂无已发布课表或历史版本"/>}
    </Spin>
  </Space>;
}
