import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Form, Input, InputNumber, message, Select, Space, Table, Tag, Typography, Upload } from 'antd';
import { planningApi as api } from '../api/planning';

export default function CurriculumMaterialsPage(){
  const [docs,setDocs]=useState<any[]>([]),[selected,setSelected]=useState<number>(),[file,setFile]=useState<File>(),[busy,setBusy]=useState(false),[checked,setChecked]=useState(false);
  const [form]=Form.useForm();
  const load=useCallback(async()=>{try{setDocs(await api.curricula());}catch(e){message.error(String(e));}},[]);
  useEffect(()=>{void load();},[load]);
  const doc=docs.find(d=>d.id===selected);
  const upload=async()=>{
    const v=await form.validateFields();if(!file)return;setBusy(true);
    try{const data=new FormData();data.append('file',file);for(const[k,value]of Object.entries(v))data.append(k,String(value));const result=await api.importCurriculum(data);await load();setSelected(result.id);setChecked(false);message.success('已解析保存原件，请逐行核对后启用');}catch(e){message.error(e instanceof Error?e.message:'导入失败');}finally{setBusy(false);}
  };
  return <Space orientation="vertical" size="large" style={{width:'100%'}}>
    <Typography.Title level={3}>培养方案原件与版本</Typography.Title>
    <Alert showIcon type="info" title="上传→解析预览→核对启用→按周期生成任务" description="支持Excel（.xlsx）、CSV与DOCX课程表。Excel自动检查所有工作表，兼容标题行、最多三行组合表头及“总课时”“建议修读学期”等字段；不支持旧版.xls，请先另存为.xlsx。讲座计分说明、参考值、公式和无课程名称的原始行会保留为待核对条目，不阻止其他有效课程解析，也不自动进入课程库或排课；缺少课程编码时生成SYS内部编号，不等于教务正式编码。保留周课时、上课周数和尾周备注；缺学期、零授课学时、占位及同名同学期重复条目会提示核对，暂不自动生成任务。"/>
    <Card title="上传培养方案（原件保留，不覆盖历史）"><Form form={form} layout="inline" initialValues={{major:'视觉传达设计',cohort:'2026',revision:1}}>
      <Form.Item name="major" label="专业" rules={[{required:true}]}><Input/></Form.Item><Form.Item name="cohort" label="入学届次" rules={[{required:true}]}><Input/></Form.Item><Form.Item name="revision" label="修订号"><InputNumber min={1}/></Form.Item>
    </Form><Space wrap style={{marginTop:20}}><Upload maxCount={1} accept=".csv,.xlsx,.docx" beforeUpload={f=>{setFile(f);return false;}} onRemove={()=>setFile(undefined)}><Button>选择方案文件</Button></Upload><Button type="primary" disabled={!file} loading={busy} onClick={()=>void upload()}>上传并解析</Button></Space></Card>
    <Select aria-label="培养方案版本" placeholder="选择已上传方案" value={selected} onChange={v=>{setSelected(v);setChecked(false);}} options={docs.map(d=>({value:d.id,label:`${d.major} · ${d.cohort} · 修订${d.revision}${d.active?'（已启用）':''}`}))}/>
    {doc&&<Card title={`${doc.name} · 原件SHA-256 ${doc.sha256.slice(0,16)}…`}>
      <Alert type="info" showIcon style={{marginBottom:16}} title={`共${doc.rows.length}条原始记录；${doc.rows.filter((r:any)=>r.schedulable!==false&&(!r.category||r.category.startsWith('专业'))).length}条可参与专业任务生成`} description="专业课任务生成仅取所选学期的专业课程；公共课及待核对条目仍保留在原件和预览中。SYS编号为内部追踪用，重复记录不会擅自合并。"/>
      <Table rowKey="code" dataSource={doc.rows} pagination={{pageSize:20}} scroll={{x:1900}} columns={[{title:'来源工作表/行',render:(_,r:any)=>`${r.source_sheet||`表${r.source_table}`} / ${r.source_row}`},{title:'课程编码',render:(_,r:any)=><>{r.code}{r.code_generated&&<Tag>内部编号</Tag>}</>},{title:'课程名称',render:(_,r:any)=>r.name||'（无课程名称，原始行待核对）'},{title:'学分',dataIndex:'credits'},{title:'学时',dataIndex:'required_hours'},{title:'培养学期',render:(_,r:any)=>r.semester??'待核对'},{title:'课程性质',dataIndex:'category'},{title:'周课时',dataIndex:'weekly_hours'},{title:'上课周数',dataIndex:'teaching_weeks'},{title:'尾周课时',dataIndex:'tail_hours'},{title:'原始备注',dataIndex:'notes'},{title:'核对提示',width:260,render:(_,r:any)=>(r.review_notes||[]).join('；')},{title:'方向',dataIndex:'direction'},{title:'领域',render:(_,r:any)=>r.tags.join('、')}]}/>
      <Space wrap>{doc.active&&<Button loading={busy} onClick={async()=>{setBusy(true);try{const result=await api.syncCurriculumCourses(doc.id);message.success(`课程库新增${result.added}门，复用${result.reused}门`);}catch(e){message.error(String(e));}finally{setBusy(false);}}}>补齐课程库</Button>}<Checkbox checked={checked} onChange={e=>setChecked(e.target.checked)}>已逐行核对课程、学时、学分与开课学期</Checkbox><Button type="primary" disabled={!checked||doc.active} loading={busy} onClick={async()=>{setBusy(true);try{const result=await api.activateCurriculum(doc.id);await load();message.success(`已启用，课程库新增${result.course_library.added}门、复用${result.course_library.reused}门`);}catch(e){message.error(String(e));}finally{setBusy(false);}}}>{doc.active?'已启用':'确认启用'}</Button></Space>
    </Card>}
  </Space>;
}
