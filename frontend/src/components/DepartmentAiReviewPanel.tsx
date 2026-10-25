import {useEffect, useRef, useState} from 'react';
import {Alert, Button, Card, Collapse, Empty, Select, Space, Table, Tag, Typography} from 'antd';
import {RobotOutlined, SafetyCertificateOutlined} from '@ant-design/icons';
import {planningApi} from '../api/planning';

const levelNames:Record<string,string>={blocking:'冲突/超限',warning:'风险提示',unknown:'待核实'};

export default function DepartmentAiReviewPanel({planId,admin,version,disabled}:{planId:number;admin:boolean;version:unknown;disabled:boolean}){
  const [units,setUnits]=useState<{id:number;name:string}[]>([]);
  const [unitId,setUnitId]=useState<number>();
  const [report,setReport]=useState<any>();
  const [running,setRunning]=useState<'ai'|'rules'>(),[error,setError]=useState('');
  const busy=Boolean(running);
  const [level,setLevel]=useState<string>();
  const generation=useRef(0);
  const activeScope=useRef({active:true});
  useEffect(()=>{
    if(admin)void planningApi.offeringUnits().then(setUnits).catch(()=>setError('教研室列表加载失败'));
  },[admin]);
  useEffect(()=>{
    const scope={active:true};activeScope.current=scope;
    generation.current++;setReport(undefined);setError('');setRunning(undefined);
    return()=>{scope.active=false;};
  },[planId,unitId,version]);
  const analyze=async(useAi:boolean)=>{
    const scope=activeScope.current;
    const request=++generation.current;setRunning(useAi?'ai':'rules');setError('');
    try{
      const next=await planningApi.departmentAiReview(planId,{use_ai:useAi,unit_id:unitId});
      if(scope.active&&request===generation.current)setReport(next);
    }catch(e){if(scope.active&&request===generation.current){setReport(undefined);setError(e instanceof Error?e.message:'审查失败，请重试');}}
    finally{if(scope.active&&request===generation.current)setRunning(undefined);}
  };
  const rows=(report?.applications||[]).filter((r:any)=>!level||r.issues.some((i:any)=>i.level===level));
  const levelOrder:Record<string,number>={blocking:0,warning:1,unknown:2};
  const priorities=(report?.applications||[]).flatMap((r:any)=>r.issues.map((issue:any)=>({...issue,course_name:r.course_name,group:r.group})))
    .sort((a:any,b:any)=>(levelOrder[a.level]??3)-(levelOrder[b.level]??3)).slice(0,3);
  return <Card size="small" title="教研室教师课程 AI 审查" extra={<Space>
    <Button icon={<SafetyCertificateOutlined/>} loading={running==='rules'} disabled={disabled||busy} onClick={()=>void analyze(false)}>规则检查</Button>
    <Button type="primary" icon={<RobotOutlined/>} loading={running==='ai'} disabled={disabled||busy} onClick={()=>void analyze(true)}>AI 审查</Button>
  </Space>}>
    <Space wrap style={{marginBottom:12}}>
      {admin&&<Select aria-label="AI审查教研室" allowClear placeholder="全学院教研室" value={unitId} onChange={setUnitId} style={{width:210}} options={units.map(u=>({value:u.id,label:u.name}))}/>}
      <Select aria-label="AI审查问题类型" allowClear placeholder="全部审查结果" value={level} onChange={setLevel} style={{width:170}} options={Object.entries(levelNames).map(([value,label])=>({value,label}))}/>
      {report&&<><Tag color={report.source==='llm'?'purple':'default'}>{report.source==='llm'?`AI · ${report.model}`:'规则分析'}</Tag><Typography.Text type="secondary">{report.unit_name} · {report.stats.teachers}名教师 · {report.stats.applications}项申请 · {new Date(report.generated_at).toLocaleTimeString()}</Typography.Text></>}
    </Space>
    {error&&<Alert type="error" showIcon title={error} style={{marginBottom:12}}/>}
    {report?<>
      {report.reason&&<Alert type="info" showIcon title={report.reason} style={{marginBottom:12}}/>}
      <Space wrap style={{marginBottom:12}}><Tag color="red">冲突/超限 {report.stats.blocking}</Tag><Tag color="orange">风险 {report.stats.warnings}</Tag><Tag>待核实 {report.stats.unknown}</Tag></Space>
      {priorities.length?<div style={{marginBottom:12}}><Typography.Text strong>优先关注</Typography.Text>{priorities.map((issue:any,index:number)=><div key={index}><Tag color={issue.level==='blocking'?'red':issue.level==='warning'?'orange':'default'}>{levelNames[issue.level]}</Tag><Typography.Text strong>{issue.course_name} · {issue.group}</Typography.Text><Typography.Text>：{issue.message}</Typography.Text></div>)}</div>:<Typography.Paragraph type="secondary">当前结果未列出需优先处理的问题。</Typography.Paragraph>}
      <Collapse items={[{key:'details',label:'展开审查说明与逐项详情',children:<>
      <Typography.Paragraph style={{whiteSpace:'pre-wrap'}}>{report.text}</Typography.Paragraph>
      {!!report.teacher_aliases?.length&&<Typography.Paragraph type="secondary">{report.teacher_aliases.map((a:any)=>`${a.alias}：${a.teacher_name}`).join('；')}</Typography.Paragraph>}
      <Table<any> rowKey={r=>`${r.submission_id}-${r.task_id}`} size="small" dataSource={rows} pagination={{pageSize:8}} scroll={{x:850}} columns={[
        {title:'教师',dataIndex:'teacher_name',width:100},
        {title:'课程 / 班级',render:(_,r)=><><Typography.Text strong>{r.course_name}</Typography.Text><div>{r.group}</div><Typography.Text type="secondary">{r.plan_name}</Typography.Text></>},
        {title:'专业匹配',width:110,render:(_,r)=>r.professional_fit==null?<Tag>资料待核实</Tag>:<Tag color={r.professional_fit<60?'orange':'green'}>{r.professional_fit}%</Tag>},
        {title:'综合推荐',width:110,render:(_,r)=>r.raw_total==null?'待核实':`${r.raw_total}/${r.maximum}`},
        {title:'冲突与风险',render:(_,r)=>r.issues.length?r.issues.map((i:any,index:number)=><div key={index} style={{marginBottom:5}}><Tag color={i.level==='blocking'?'red':i.level==='warning'?'orange':'default'}>{levelNames[i.level]}</Tag>{i.message}</div>):<Typography.Text type="secondary">当前数据中未检出问题</Typography.Text>},
      ]} expandable={{expandedRowRender:r=><Space orientation="vertical" style={{width:'100%'}}>
        <Typography.Text>教师方向：{r.teacher_direction||'未填写'}；课程方向：{r.course_direction||'未填写'}；擅长课程：{r.skilled_course_match?'命中':'未命中'}</Typography.Text>
        <Typography.Text>教师领域：{r.teacher_tags.join('、')||'未填写'}；课程领域：{r.course_tags.join('、')||'未填写'}</Typography.Text>
        <Typography.Text type="secondary">{r.explanation}</Typography.Text>
        <Space wrap>{r.components.map((c:any)=><Tag key={c.name}>{c.name}：{c.score??'未知'}/{c.maximum}{c.hits?.length?` · ${c.hits.join('、')}`:''}</Tag>)}</Space>
      </Space>}}/>
      </>}]} />
    </>:<Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未生成审查结果"/>}
  </Card>;
}
